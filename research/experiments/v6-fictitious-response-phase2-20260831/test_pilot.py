import math
from pathlib import Path
import random
from types import SimpleNamespace

import pytest
import torch
import run_pilot as run
import oracle_stats as stats
import review_finish as review
from alpha_holdem.train_v5 import build_group_opponent_assignments, initial_environment_hand_accounting
from alpha_holdem.policy_contract_v6 import validate_resume, METADATA


def test_new_ppo_config_not_sl_resume_or_legacy_rebind(monkeypatch):
    monkeypatch.setattr(run, 'parent_check', lambda: None)
    cmd = run.training_command()
    assert cmd[:3] == ['-u', str(run.BASE/'execution_code/source_files/scripts/alpha_holdem/train_v5.py'), '--device']
    for flag, expected in {
        '--total-environment-hands':'2097152', '--seed':'20261018', '--worker-seed-base':'2026101800',
        '--resume':str(run.BASE/'frozen/average.pt'), '--self-play-fraction':'0', '--source-policy-kl-coef':'0',
        '--workers':'12', '--rollout-mode':'multi', '--rollout-envs-per-worker':'8',
        '--ppo-epochs':'2', '--ppo-target-kl':'.01', '--mini-batch-size':'1024',
        '--archive-checkpoint-every':'4', '--save-interval':'1'
    }.items(): assert cmd[cmd.index(flag)+1] == expected
    assert all(flag in cmd for flag in ('--allow-resume', '--reset-optimizer', '--reset-hand-counter', '--validate-stream'))
    assert all(flag not in cmd for flag in ('--v6-rebind-legacy-weights', '--no-reset-optimizer', '--source-policy-reference-checkpoint', '--ppo-replay-ratio'))
    start = cmd.index('--fixed-opponent-checkpoints')+1
    end = next(i for i in range(start,len(cmd)) if cmd[i].startswith('--'))
    assert cmd[start:end] == [str(run.BASE/'frozen/average.pt')]
    assert cmd[cmd.index('--run-id')+1] != run.PARENT.name


def test_source_initialization_is_exact_and_does_not_mutate_sl_checkpoint():
    torch.set_num_threads(1)
    source = run.PARENT/'frozen/student.pt'
    before = run.sha(source)
    report = run.initialization_check(source)
    assert report['identical_initial_tensors'] == report['new_trainable_parameters'] == 86
    assert report['source_optimizer_states_preserved'] == 80 and report['new_optimizer_states'] == 0
    assert report['source_optimizer_steps_preserved'] == 1024
    assert report['initial_actual_hands'] == 0 and report['old_hands_not_recounted'] == 262144
    assert run.sha(source) == before == run.MODEL_SHA


def test_v6_checkpoint_is_not_legacy_rebound():
    args = SimpleNamespace(env_version='v6', v6_rebind_legacy_weights=False)
    validate_resume(args, METADATA)
    with pytest.raises(ValueError): validate_resume(args, {})
    args = SimpleNamespace(env_version='v6', v6_rebind_legacy_weights=True, starting_stack=200,
        resume='source.pt', allow_resume=True, reset_optimizer=True, reset_hand_counter=True)
    with pytest.raises(ValueError): validate_resume(args, METADATA)


def test_sl_accounting_is_not_silently_ppo_resumed():
    source = {'environment_hand_accounting':dict(completed_hands=262144, prefix_complete=True), 'total_hands':262144}
    with pytest.raises(ValueError): initial_environment_hand_accounting(source, reset_hand_counter=False, run_id='new')
    fresh = initial_environment_hand_accounting(source, reset_hand_counter=True, run_id='new')
    assert fresh['completed_hands'] == 0 and fresh['origin_run_id'] == 'new' and fresh['unknown_prefix_training_marker_hands'] == 0
    assert source['environment_hand_accounting']['completed_hands'] == 262144


def test_all_groups_pin_one_average_no_selfplay():
    rng, replay = random.Random(run.SEED), random.Random(run.SEED)
    rows = []
    for i in range(20):
        a, meta = build_group_opponent_assignments(12, 1, 8, 0, rng, [1.0])
        b, other = build_group_opponent_assignments(12, 1, 8, 0, replay, [1.0])
        assert list(a) == list(b) == [0]*12 and meta == other
        rows.append(dict(applies_to_iteration=i+1, group_metadata=meta['groups'],
            workers=[dict(worker_id=w, opponent={'kind':'pool_snapshot'}) for w in range(12)]))
    assert stats.exposure(rows, 20)['selfplay_worker_slots'] == 0
    assert stats.exposure(rows, 20)['average_worker_slots'] == 240
    rows[-1]['group_metadata'][0]['opponent_id'] = -1
    with pytest.raises(AssertionError): stats.exposure(rows, 20)


def test_first_actual_archive_not_filename_or_score():
    archives = [dict(iteration=4, actual_hands=200, filename_hands=1000, score=100),
                dict(iteration=8, actual_hands=500, filename_hands=2000, score=-999),
                dict(iteration=12, actual_hands=750, filename_hands=3000, score=999)]
    assert stats.select_first_actual(list(reversed(archives)), 256) is archives[1]
    assert stats.select_first_actual(archives, 500) is archives[1]
    assert stats.select_first_actual(archives, 501) is archives[2]
    with pytest.raises(StopIteration): stats.select_first_actual(archives, 1000)
    with pytest.raises(ValueError): stats.select_first_actual(archives+[archives[0]], 100)
    with pytest.raises(ValueError): stats.select_first_actual([dict(iteration=4, actual_hands=500), dict(iteration=8, actual_hands=400)], 256)


@pytest.mark.parametrize('values', [[], [1], [0,math.nan], [0,math.inf]])
def test_invalid_arithmetic(values):
    for function in (stats.estimate, review.interval):
        with pytest.raises(ValueError): function(values)


@pytest.mark.parametrize('values', [[0]*8, [-100,100,300], [-19990,20000,17.3,-20.1]])
def test_independent_arithmetic(values):
    a, b = stats.estimate(values), review.interval(values)
    for key in a: assert a[key] == pytest.approx(b[key])
    assert a['family25_ci95'][0] <= a['ci95'][0] <= a['ci95'][1] <= a['family25_ci95'][1]


def test_primary_gate_is_not_point_estimate_or_external_admission():
    assert stats.decision(dict(bb_per_100=5, ci95=[-2,12])) == 'RESPONSE_LEARNING_GATE_NOT_PASSED'
    assert stats.decision(dict(bb_per_100=5, ci95=[0,10])) == 'RESPONSE_LEARNING_GATE_NOT_PASSED'
    assert stats.decision(dict(bb_per_100=5, ci95=[1,9])) == 'ADMIT_SEPARATE_AVERAGE_UPDATE'


def test_32_fixed_cells_and_no_training_deal_seed_reuse():
    assert run.EVAL_HANDS == 262144 and run.PAIRS == 4096 and run.EVAL_SEED == 20261019
    assert run.EVAL_SEED != run.SEED and len(run.LABELS) == 4 and len(run.OPPONENTS) == 8
    for label in run.LABELS:
        for opponent in run.OPPONENTS:
            cmd = run.eval_command(label, opponent)
            assert cmd[cmd.index('--device')+1] == 'cpu'
            assert cmd[cmd.index('--pairs')+1] == '4096'
            assert Path(cmd[cmd.index('--anchor')+1]).stem == opponent
    with pytest.raises(AssertionError): run.eval_command('best', 'average')


def test_raw_cell_rejects_mutated_deck_index_reward_and_truncation():
    decks = [list(range(52)), list(reversed(range(52)))]
    rows = [dict(pair_index=i, deck=d, rewards_bb=[-1,2], decisions=[2,3]) for i,d in enumerate(decks)]
    assert review.raw_values(rows, decks) == [50,50]
    with pytest.raises(ValueError): review.raw_values(rows[:-1], decks)
    rows[1]['rewards_bb'] = [201,0]
    with pytest.raises(AssertionError): review.raw_values(rows, decks)
    rows[1]['rewards_bb'] = [-1,2]
    rows[1]['pair_index'] = 0
    with pytest.raises(AssertionError): review.raw_values(rows, decks)


def test_complete_raw_line_accounting(tmp_path):
    path = tmp_path/'pairs.jsonl'
    assert stats.raw_count(path) == 0
    path.write_bytes(b'{}\n{}\n{')
    assert stats.raw_count(path) == 2


def valid_parent():
    return dict(status='COMPLETED'), dict(status='PASS',decision='ADMIT_NEXT_RESPONSE_PHASE',
        candidate_sha256=run.MODEL_SHA,evaluation_hands=172032,new_training_hands=0,slumbot_hands=0,
        qualification_hands=0,goal_achieved=False,external_admission=False,
        primary_contrasts={k:dict(family2_ci95=[1.,3.]) for k in ('hedge_against_response','retain_anchor1_2_vs_response')})


def test_parent_gate_requires_independent_complete_positive_diagnostics():
    record,result = valid_parent()
    assert stats.parent_gate(record,result,run.MODEL_SHA)
    record['status'] = 'RUNNING'
    assert not stats.parent_gate(record,result,run.MODEL_SHA)


@pytest.mark.parametrize('key,value',[('evaluation_hands',172030),('candidate_sha256','wrong'),
    ('slumbot_hands',1),('new_training_hands',1),('goal_achieved',True),('external_admission',True),
    ('decision','AVERAGE_STRATEGIC_GATE_NOT_PASSED')])
def test_parent_evidence_mutations_rejected(key,value):
    record,result = valid_parent()
    result[key]=value
    assert not stats.parent_gate(record,result,run.MODEL_SHA)


@pytest.mark.parametrize('lower',[0.,-1.,math.nan])
def test_both_adjusted_primary_lowers_required(lower):
    record,result = valid_parent()
    result['primary_contrasts']['hedge_against_response']['family2_ci95'][0]=lower
    assert not stats.parent_gate(record,result,run.MODEL_SHA)


def test_pending_parent_forbids_real_execution(monkeypatch):
    monkeypatch.setattr(run,'PARENT_SHA',None)
    with pytest.raises(ValueError,match='not yet admitted'):
        run.parent_check()


def test_real_parent_admission_after_hash_freeze():
    if run.PARENT_SHA is None:
        pytest.skip('Fixed strategic cohort still running; parent review SHA unset')
    run.parent_check()


def test_half_checkpoint_is_previous_budget_and_primary_family25():
    assert run.TARGET//2 == 1048576 and run.TARGET//4 == 524288
    assert (len(run.LABELS)-1)*len(run.OPPONENTS)+1 == 25
