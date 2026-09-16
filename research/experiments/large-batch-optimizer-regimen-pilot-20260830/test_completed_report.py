import importlib.util
from pathlib import Path
import sys

import pytest

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
spec = importlib.util.spec_from_file_location('pilot_report', BASE / 'report_completed_pilot.py')
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def row(n, epochs=2, iteration=1):
    return dict(iteration=iteration, fresh_policy_rows=n, ppo_epochs_completed=epochs,
                ppo_replay_rows=0, policy_rows=n, value_head_catchup_enabled=False)


def test_full_and_partial_steps():
    result = report.batch_accounting([row(27000), row(32768, 1, 2)], 16384)
    assert result['total_steps'] == 6
    assert result['full_batch_steps'] == 4
    assert result['partial_batch_steps'] == 2
    assert result['updates'][0]['partial_batch_rows'] == 10616
    assert result['transition_presentations'] == 86768
    report.validate_steps(result, [6.0]*10)


def test_reject_reset_or_missing_adam_state():
    for states in [[5.0]*10, [6.0]*9, [6.0]*9+[7.0]]:
        with pytest.raises(ValueError):
            report.validate_steps({'total_steps': 6}, states)


def test_printed_value_losses_preserve_precision_and_order():
    assert report.rounded_value_losses('[    1] hands=4 vloss=0.012345 ent=.5\n[  2] vloss=0.2 ent=.4', 2) == [.012345, .2]
    with pytest.raises(ValueError):
        report.rounded_value_losses('[1] vloss=0.1 end\n[1] vloss=0.2 end', 2)


@pytest.mark.parametrize('field,value', [('iteration', 2), ('fresh_policy_rows', 0),
    ('ppo_epochs_completed', 0), ('ppo_replay_rows', 1), ('policy_rows', 15),
    ('value_head_catchup_enabled', True)])
def test_reject_unsupported_reconstruction(field, value):
    sample = row(27000)
    sample[field] = value
    with pytest.raises(ValueError):
        report.batch_accounting([sample], 16384)
