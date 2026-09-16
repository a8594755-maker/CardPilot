import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_guarded_followthrough import eval_argv, last_metric, validate_original_audit


def audit():
    return {'session_independence': {'seeds': True, 'assignments': True}, 'runs': [
        {'name': f'seed{seed}', 'physical_environment_hands': 4194304,
         'gates': {'corrected_legacy_contract_bound': False, 'replay_cumulative_exact': True,
                   'resume_controls_exact': seed != 2, 'physical_accounting_exact': seed != 2}}
        for seed in (1,2,3)]}


def test_only_known_failures_can_reach_independent_verifier():
    validate_original_audit(audit())


@pytest.mark.parametrize('fault', ['replay', 'wrong_seed', 'independence', 'target'])
def test_new_failure_stops_before_evaluation(fault):
    data = copy.deepcopy(audit())
    if fault == 'replay':
        data['runs'][1]['gates']['replay_cumulative_exact'] = False
    elif fault == 'wrong_seed':
        data['runs'][0]['gates']['resume_controls_exact'] = False
    elif fault == 'independence':
        data['session_independence']['seeds'] = False
    else:
        data['runs'][2]['physical_environment_hands'] -= 1
    with pytest.raises(RuntimeError):
        validate_original_audit(data)


def test_exact_preregistered_evaluation_parameters():
    for seed in (1,2,3):
        args = eval_argv(seed)
        assert args[args.index('--seed')+1] == str(20263280+seed)
        assert args[args.index('--pairs-per-anchor')+1] == '2048'
        assert args.count('--anchor') == 4
        assert args[args.index('--control')+1].endswith(f'2m-scale-20260904/seed{seed}/latest.pt')
        assert args[args.index('--treatment')+1].endswith(f'4m-scale-20260904/seed{seed}/latest.pt')


def test_complete_metric_tail_not_half_written_row(tmp_path):
    path = tmp_path/'metrics.jsonl'
    path.write_text(json.dumps({'iteration': 10})+'\n'+ '{"iteration":')
    assert last_metric(path)['iteration'] == 10
