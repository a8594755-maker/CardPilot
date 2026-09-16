import copy
import math
import pytest
from run_benchmark import ARMS, ROOT, select, summarize, training_command


def fixture():
    rows = []
    for i in [1, 2, 3]:
        rows.append(dict(iteration=i, hands=90*i, environment_hand_accounting=dict(completed_hands=100*i,
                         prefix_complete=True, unknown_prefix_training_marker_hands=0,
                         session_worker_counts=[dict(completed_hands=100*i)]), approx_kl=.01,
                         reference_policy_kl=.02, reference_policy_kl_coef=.01, ppo_replay_rows=0,
                         ppo_replay_buffer_iterations=0, ppo_epochs_completed=2))
    text = '\n'.join(f'[{i}] hands={90*i} envhands={100*i} other=x inf_bs=4.0 collect=2.0s ppo=1.0s' for i in [1, 2, 3])
    return text, rows


def test_exact_commands():
    for label, mode, slots in ARMS:
        cmd = training_command(label, mode, slots)
        assert cmd[cmd.index('--rollout-mode')+1] == mode
        assert cmd[cmd.index('--rollout-envs-per-worker')+1] == str(slots)
        assert cmd[cmd.index('--total-environment-hands')+1] == '32768'
        assert cmd[cmd.index('--resume')+1] == str(ROOT/'models/baseline/standard10/latest.pt')
        assert all(flag in cmd for flag in ['--validate-stream', '--reset-hand-counter', '--reset-optimizer', '--v6-rebind-legacy-weights'])
        assert cmd[cmd.index('--source-policy-kl-coef')+1] == '.01'


def test_summarize_exact_windows_and_tail():
    text, rows = fixture()
    r = summarize(text, rows, 305, 12, target=250)
    assert r['all_updates']['physical_hands'] == 300
    assert r['excluding_update1']['physical_hands'] == 200
    assert r['excluding_update1']['physical_hands_per_logged_second'] == 200/6
    assert r['physical_hands_per_trainer_wall_second'] == 305/12
    assert r['overshoot'] == 55 and r['shutdown_counter_tail'] == 5


@pytest.mark.parametrize('kind', ['missing', 'order', 'counter', 'unknown', 'worker', 'nan', 'replay', 'early', 'elapsed'])
def test_bad_evidence_rejected(kind):
    text, rows = fixture()
    elapsed, target = 12, 250
    if kind == 'missing': rows.pop()
    if kind == 'order': rows[1]['iteration'] = 1
    if kind == 'counter': rows[1]['hands'] += 1
    if kind == 'unknown': rows[1]['environment_hand_accounting']['prefix_complete'] = False
    if kind == 'worker': rows[1]['environment_hand_accounting']['session_worker_counts'][0]['completed_hands'] = 1
    if kind == 'nan': rows[1]['approx_kl'] = float('nan')
    if kind == 'replay': rows[1]['ppo_replay_rows'] = 1
    if kind == 'early': target = 199
    if kind == 'elapsed': elapsed = math.inf
    with pytest.raises(ValueError): summarize(text, rows, 305, elapsed, target=target)


def test_selection_requires_two_speed_metrics_and_all_health():
    rows = [dict(arm=label, slots=slots, health='PASS', physical_hands_per_trainer_wall_second=rate,
                 excluding_update1=dict(physical_hands_per_logged_second=rate))
            for (label, _, slots), rate in zip(ARMS, [100, 126, 200])]
    assert select(rows) == 'multi8'
    rows[2]['excluding_update1']['physical_hands_per_logged_second'] = 124
    assert select(rows) == 'multi4'
    rows[1]['physical_hands_per_trainer_wall_second'] = 124
    assert select(rows) == 'single1'
    rows[2]['health'] = 'FAIL'
    with pytest.raises(ValueError): select(rows)
