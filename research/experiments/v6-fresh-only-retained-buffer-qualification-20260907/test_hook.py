import ast
from pathlib import Path
import pytest
from hook import OLD,NEW,transformed

SOURCE='def main():\n    if '+OLD+':\n        raise ValueError("guard")\n    return 1\n'

def test_only_guard_changes():
    expected=ast.parse(SOURCE.replace(OLD,NEW))
    assert ast.dump(transformed(SOURCE))==ast.dump(expected)

@pytest.mark.parametrize('text',['def main(): pass',SOURCE+SOURCE,SOURCE.replace('!=','==')])
def test_drift_fails(text):
    with pytest.raises(ValueError): transformed(text)

@pytest.mark.parametrize('buffer,ratio,allowed',[(2,0,True),(2,.5,True),(0,0,True),(0,.5,False)])
def test_guard_contract(buffer,ratio,allowed):
    from types import SimpleNamespace
    scope={'args':SimpleNamespace(ppo_replay_buffer_iterations=buffer,ppo_replay_ratio=ratio)}
    exec(compile(transformed(SOURCE),'<fixture>','exec'),scope)
    if allowed: assert scope['main']()==1
    else:
        with pytest.raises(ValueError): scope['main']()

def test_real_frozen_main_only_guard_changed():
    p=Path(__file__).resolve().parents[1]/'v6-preflop-actor-trunk-route-qualification-20260906/candidate/scripts/alpha_holdem/train_v5.py'
    source=p.read_text(encoding='utf-8')
    original=ast.parse(source)
    original.body=[n for n in original.body if isinstance(n,ast.FunctionDef) and n.name=='main']
    replacement=ast.parse(source.replace(OLD,NEW))
    replacement.body=[n for n in replacement.body if isinstance(n,ast.FunctionDef) and n.name=='main']
    assert ast.dump(transformed(source))==ast.dump(replacement)
    assert ast.dump(original)!=ast.dump(replacement)
