from pathlib import Path
import sys
import pytest
import candidate

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from research.experiment_log import command_audit as legacy


@pytest.mark.parametrize('command', [
    'python -c "x=1\nassert x<2\nassert x>0"',
    'python -u -c "value={\'a\':3}; assert value[\'a\']>0"',
    'py -c "same=2; bounded=3; assert same<bounded"',
    'python.exe -c "print(1)"',
    'python -c \'print("literal")\'',
    'python -c "assert 0<1<2"',
    'python -c "x=2; assert 1<x>0"',
    'python -c "x=[1]; y=x[...]"',
])
def test_literal_python_is_not_flattened_into_shell_placeholders(command):
    assert candidate.command_audit(command, legacy)['exact']


@pytest.mark.parametrize('command', [
    'python -c "print(\'<path>\')"',
    'python -c "print(\'{input}\')"',
    'python -c "print(\'...\')"',
    'python -c "..."',
    'python -c "def f():\n    ..."',
    'python -c "assert x<"',
    'python -c ""',
    'python -c "x=$value"',
    'python -c "print(`\'x`\')"',
    'python -c "print(1)" extra',
    'python -c "print(1)"; python -c "print(2)"',
    'python -c print(1)',
])
def test_incomplete_or_ambiguous_inline_commands_stay_flagged(command):
    assert not candidate.command_audit(command, legacy)['exact']


@pytest.mark.parametrize('command', [
    'python scripts/alpha_holdem/train_v5.py --seed 20260930',
    'python train.py --model <path>',
    'python train.py --out "<path with spaces>"',
    'same command followed by evaluation',
    'pwsh -File run.ps1 -Target 100',
    'node script.js',
    '',
])
def test_non_inline_behavior_is_unchanged(command):
    assert candidate.command_audit(command, legacy) == legacy(command)


def test_payload_is_never_executed(tmp_path):
    path=(tmp_path/'must_not_exist.txt').as_posix()
    command=f'python -c "open(\'{path}\',\'w\').write(\'side effect\')"'
    assert candidate.command_audit(command, legacy)['exact']
    assert not Path(path).exists()


def test_two_operator_false_positive_is_reproduced_before_fix():
    command='python -c "assert first[\'hands\']<current[\'hands\']\nassert min(steps)>max(old_steps)"'
    assert legacy(command)['reasons']==['contains_placeholder']
    assert candidate.command_audit(command, legacy)['exact']
