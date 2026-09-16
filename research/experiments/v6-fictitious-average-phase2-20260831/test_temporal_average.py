import copy
import io
import math
from pathlib import Path
import sys

import numpy as np
import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from temporal_average import Reservoir, KEYS, SHAPES, hand_spec, uniform_for, softmax_legal, select, soft_ce, observation_digest


def obs():
    result = {k: np.zeros(s, dtype=np.float32) for k, s in zip(KEYS, SHAPES)}
    result['legal_mask'][:] = 1
    return result


def test_reservoir_algorithm_r_independent_reference_and_roundtrip():
    import random
    r, rng, ids = Reservoir(7, 311), random.Random(311), []
    for i in range(100):
        o = obs()
        o['extra_info'][0] = i
        r.add(o, np.ones(9)/9, (i, 0))
        if i < 7:
            ids.append(i)
        else:
            j = rng.randrange(i+1)
            if j < 7:
                ids[j] = i
    assert list(r.ids[:, 0]) == ids and r.seen == 100
    buffer = io.BytesIO()
    torch.save(r.state_dict(), buffer)
    buffer.seek(0)
    restored = Reservoir.restore(torch.load(buffer, weights_only=False))
    for i in range(100, 130):
        for reservoir in (r, restored):
            reservoir.add(obs(), np.ones(9)/9, (i, 0))
    assert r.rng.getstate() == restored.rng.getstate()
    assert np.array_equal(r.ids, restored.ids)
    assert np.array_equal(r.targets, restored.targets)
    for k in KEYS:
        assert np.array_equal(r.arrays[k], restored.arrays[k])


def test_reservoir_is_not_recent_window_or_prefix_only():
    r = Reservoir(20, 37)
    for i in range(200):
        r.add(obs(), np.ones(9)/9, (i, 0))
    assert r.ids[:, 0].min() < 100 and r.ids[:, 0].max() >= 100
    assert len(set(map(tuple, r.ids))) == 20


def test_reservoir_snapshot_does_not_alias_live_data():
    r = Reservoir(1, 1)
    r.add(obs(), np.ones(9)/9, (0, 0))
    saved = r.state_dict()
    r.targets[:] = 0
    assert np.all(saved['targets'] > 0)


@pytest.mark.parametrize('bad', [0, -1, 1.5])
def test_bad_capacity(bad):
    with pytest.raises(ValueError):
        Reservoir(bad, 1)


def test_separate_deck_teacher_action_streams_and_order_independence():
    specs = [hand_spec(553, i, 17) for i in range(2000)]
    assert all(sorted(d) == list(range(52)) for d, _ in specs)
    assert len({tuple(d) for d, _ in specs}) == 2000
    assert all(hand_spec(553, i, 17) == specs[i] for i in reversed(range(2000)))
    assert all(hand_spec(553, i, 2)[0] == specs[i][0] for i in range(2000))
    assert all(hand_spec(554, i, 17)[0] != specs[i][0] for i in range(2000))
    pairs = {tuple(t) for _, t in specs}
    assert len(pairs) > 280 and sum(t[0] == t[1] for _, t in specs) < 200
    assert uniform_for(553, 0, 0, 0) != uniform_for(553, 0, 1, 0)
    assert uniform_for(553, 0, 0, 0) != uniform_for(553, 0, 0, 1)


def test_whole_episode_mixture_requires_reach_weighting():
    # Two equiprobable policies reach a later infoset with .9 and .1.
    # Their later probabilities of action A are .8 and .2.
    reaches, actions = [.9, .1], [.8, .2]
    conditional = sum(.5*r*a for r, a in zip(reaches, actions))/sum(.5*r for r in reaches)
    assert math.isclose(conditional, .74)
    assert not math.isclose(conditional, np.mean(actions))
    # Integer population of whole episodes reproduces the conditional mixture.
    population = [actions[0]]*900 + [actions[1]]*100
    assert math.isclose(np.mean(population), conditional)


def test_masked_probabilities_and_endpoint_draws():
    mask = np.array([[1, 0, 1, 0, 0, 0, 0, 0, 0]])
    p = softmax_legal(np.zeros((1, 9)), mask)[0]
    assert list(p[[0, 2]]) == [.5, .5] and np.all(p[mask[0] == 0] == 0)
    assert select(p, 0) == 0 and select(p, .5) == 2 and select(p, np.nextafter(1., 0.)) == 2
    with pytest.raises(ValueError):
        select(p, 1.)


@pytest.mark.parametrize('kind', ['no_legal', 'nan', 'bad_mask'])
def test_invalid_batch(kind):
    logits, mask = np.zeros((1, 9)), np.ones((1, 9))
    if kind == 'no_legal':
        mask[:] = 0
    elif kind == 'nan':
        logits[0, 0] = np.nan
    else:
        mask[0, 0] = .5
    with pytest.raises(ValueError):
        softmax_legal(logits, mask)


def test_soft_target_ce_gradient_and_illegal_target_rejection():
    logits = torch.zeros(1, 9, requires_grad=True)
    masks = torch.tensor([[1, 1, 0, 0, 0, 0, 0, 0, 0]])
    target = torch.tensor([[.9, .1, 0, 0, 0, 0, 0, 0, 0]])
    loss = soft_ce(logits, target, masks).mean()
    assert math.isclose(float(loss.detach()), math.log(2), rel_tol=1e-6)
    loss.backward()
    assert torch.allclose(logits.grad, torch.tensor([[-.4, .4, 0, 0, 0, 0, 0, 0, 0]]))
    bad = target.clone()
    bad[0, 1], bad[0, 2] = 0, .1
    with pytest.raises(ValueError):
        soft_ce(logits, bad, masks)


def test_observation_digest_detects_changed_amount_without_hidden_teacher_input():
    original = obs()
    changed = copy.deepcopy(original)
    changed['action_info'][0, 2, 0] = .25
    assert observation_digest(original) != observation_digest(changed)
    original['teacher_id'] = 7
    assert observation_digest(original) == observation_digest(obs())


def test_reservoir_rejects_illegal_target_before_changing_count():
    r, o = Reservoir(4, 1), obs()
    o['legal_mask'][0] = 0
    with pytest.raises(ValueError):
        r.add(o, np.ones(9)/9, (0, 0))
    assert r.seen == 0


def test_phase2_preregistered_schedule_and_identical_qualified_collector():
    import run_distillation as run
    assert run.EPOCHS == 8 and run.TEACHERS == 3
    assert run.TRAIN_HANDS == 262144 and run.VALID_HANDS == 8192
    previous = run.ROOT/'research/experiments/v6-historical-average-distillation-20260831/temporal_average.py'
    assert run.sha(previous) == run.sha(run.BASE/'temporal_average.py') == '836ad2770bd1ec725c57cf53757c26bb81ea813f72bb506e0ca71759e3c2b0db'


def test_real_parent_admission_after_hash_freeze():
    import run_distillation as run
    if run.FINAL_SHA is None or run.REVIEW_SHA is None:
        pytest.skip('Parent response2 still active; no collection admission')
    run.require_admission()


def test_missing_response_admission_fails_before_output_creation(monkeypatch, tmp_path):
    import run_distillation as run
    monkeypatch.setattr(run, 'BASE', tmp_path)
    monkeypatch.setattr(run, 'FINAL_SHA', None)
    monkeypatch.setattr(run, 'REVIEW_SHA', None)
    with pytest.raises(ValueError, match='no collection or output creation'):
        run.main()
    assert list(tmp_path.iterdir()) == []


def test_response_admission_uses_primary_ci_and_exact_final_not_other_checkpoints():
    import run_distillation as run
    digest = '1'*64
    report = dict(status='PASS', decision='ADMIT_SEPARATE_AVERAGE_UPDATE',
        training_health={'checkpoint_sha256':digest}, new_training_hands=2097152,
        evaluation_hands=262144, primary={'ci95':[1,5]}, slumbot_hands=0,
        qualification_hands=0, goal_achieved=False)
    run.validate_response_review(report, digest)
    with pytest.raises(AssertionError): run.validate_response_review(report, '2'*64)
    report['primary']['ci95'] = [-1,7]
    with pytest.raises(AssertionError): run.validate_response_review(report, digest)
    report['primary']['ci95'] = [0,8]
    with pytest.raises(AssertionError): run.validate_response_review(report, digest)


def test_three_teacher_independent_seat_sampling_preserves_deck_stream():
    rows = [hand_spec(2026102001, i, 3) for i in range(4096)]
    counts = {pair:0 for pair in [(a,b) for a in range(3) for b in range(3)]}
    for index, (deck, teachers) in enumerate(rows):
        assert deck == hand_spec(2026102001, index, 17)[0]
        counts[tuple(teachers)] += 1
    assert all(300 < v < 650 for v in counts.values())
    # These are deterministic schedule draws only, not completed poker hands.
    assert len({tuple(d) for d, _ in rows}) == 4096


def test_failed_barrier_does_not_claim_unknown_hands_are_zero(monkeypatch, tmp_path):
    import run_distillation as run
    monkeypatch.setattr(run, 'BASE', tmp_path)
    (tmp_path/'training_hands.jsonl').write_bytes(b'{}\n{}\n{')
    report = run.preserved_failure_accounting('TRAINING_DATA')
    assert report['preserved_complete_raw_lines'] == {'training':2, 'validation':0}
    assert report['additional_unserialized_terminal_hands_unknown']
    assert report['additional_unserialized_terminal_hands_upper_bound'] == 1024
    assert not report['exact_actual_hand_totals_claimed'] and not report['automatic_resume_qualified']
    assert run.preserved_failure_accounting('PREPARING')['additional_unserialized_terminal_hands_upper_bound'] == 0


def test_warmstart_is_not_a_fourth_teacher_or_recursive_average(monkeypatch):
    import run_distillation as run
    monkeypatch.setattr(run,'FINAL_SHA','1'*64)
    rows = run.teacher_specification()
    assert [r[0] for r in rows] == ['prior','response1','final']
    assert len({r[1] for r in rows}) == 3
    assert run.SOURCE_SHA not in [r[1] for r in rows]
    assert rows[0][1] == run.PRIOR_SHA and rows[1][1] == run.RESPONSE1_SHA


def test_three_way_reach_weighting_not_statewise_average():
    reaches, actions = np.array([.9,.1,.5]), np.array([.8,.2,.4])
    conditional = float((reaches*actions).sum()/reaches.sum())
    assert math.isclose(conditional, .94/1.5)
    assert not math.isclose(conditional,float(actions.mean()))


@pytest.mark.parametrize('mutated_role', ['initializer','teacher'])
def test_frozen_teacher_initializer_routing_and_tamper_detection(monkeypatch, tmp_path, mutated_role):
    import run_distillation as run
    monkeypatch.syspath_prepend(str(run.ROOT/'scripts'))
    from alpha_holdem.policy_contract_v6 import METADATA
    parent, out = tmp_path/'parent', tmp_path/'output'
    (parent/'frozen').mkdir(parents=True)
    (parent/'production').mkdir()
    out.mkdir()
    for name, number in [('prior',1),('response1',2),('final',3),('average',4)]:
        torch.save(dict(**METADATA, model={f'parameter{i}':torch.tensor(float(number)) for i in range(86)}),
                   parent/'frozen'/f'{name}.pt')
    corpus = tmp_path/'corpus.jsonl'
    corpus.write_text('{}\n')
    (parent/'reviewed_analysis.json').write_text('{}\n')
    (parent/'production/h1_training_metrics.jsonl').write_text('{}\n')
    monkeypatch.setattr(run,'BASE',out)
    monkeypatch.setattr(run,'TRAIN',parent)
    monkeypatch.setattr(run,'CORPUS',corpus)
    monkeypatch.setattr(run,'require_admission',lambda:None)
    monkeypatch.setattr(run,'log',lambda *args:None)
    for field,name in [('PRIOR_SHA','prior'),('RESPONSE1_SHA','response1'),('FINAL_SHA','final'),('SOURCE_SHA','average')]:
        monkeypatch.setattr(run,field,run.sha(parent/'frozen'/f'{name}.pt'))
    result = run.freeze_teachers()
    assert [r['index'] for r in result['teachers']] == [0,1,2]
    assert [r['role'] for r in result['teachers']] == ['warmstart_prior','response1','response2']
    assert result['normal_form_mixture_weights'] == [1/3]*3
    assert all(r['probability'] == 1/3 for r in result['teachers'])
    for index,row in enumerate(result['teachers']):
        assert torch.load(row['path'],weights_only=False)['model']['parameter0'].item() == index+1
    initializer = torch.load(result['initializer']['path'],weights_only=False)
    assert initializer['model']['parameter0'].item() == 4
    assert result['initializer']['sha256'] not in [r['sha256'] for r in result['teachers']]
    assert len(list((out/'teachers').glob('*.pt'))) == 3
    run.verify([],result)
    path = result['initializer']['path'] if mutated_role == 'initializer' else result['teachers'][0]['path']
    Path(path).write_bytes(b'changed fixture')
    with pytest.raises(AssertionError): run.verify([],result)
