import copy
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('sampled_external_protocol', Path(__file__).with_name('protocol.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def fixture():
    return dict(policy_mode='sample', temperature=1, observation_bridge_contract=p.BRIDGE,
        uniform=.8, selected_action_slot=1, greedy_action_slot=0,
        legal_mask=[1,1,0,0,0,0,0,0,0], direct_increment='c',
        v6_action_table=['f','c',None,None,None,None,None,None,None],
        legacy_selected_action_slot=2, legacy_legal_mask=[1,1,1,0,0,0,0,0,0],
        legacy_action_table=['f','c','c',None,None,None,None,None,None],
        model_probs=[.6,.4,0,0,0,0,0,0,0], behavior_probs=[.6,.4,0,0,0,0,0,0,0],
        behavior_action_probability=.2)


def test_schedule_and_commands():
    rows = p.schedule()
    assert len(rows) == 32 and sum(r['hands'] for r in rows) == 80000
    assert len({r['session_id'] for r in rows}) == len({r['policy_seed'] for r in rows}) == 32
    for arm in p.ARMS:
        assert sum(r['hands'] for r in rows if r['arm'] == arm) == 20000
    for wave in range(4):
        assert all(sum(r['wave'] == wave and r['arm'] == a for r in rows) == 2 for a in p.ARMS)
    cmd = p.session_command(rows[0], Path('runtime'))
    assert cmd[cmd.index('--policy-mode') + 1] == 'sample'
    assert cmd[cmd.index('--observation-bridge') + 1] == 'legacy-v4'
    bad = dict(rows[0], hands=100)
    with pytest.raises(ValueError):
        p.session_command(bad, Path('runtime'))


def test_non_greedy_alias_is_valid():
    p.validate_decision(fixture())


@pytest.mark.parametrize('key,value', [('policy_mode','greedy'), ('temperature',0),
    ('uniform',1), ('uniform',float('nan')), ('selected_action_slot',8),
    ('direct_increment','f'), ('behavior_action_probability',.5),
    ('behavior_probs',[.5,.5,0,0,0,0,0,0,0])])
def test_mutations_rejected(key, value):
    d = copy.deepcopy(fixture())
    d[key] = value
    with pytest.raises(ValueError):
        p.validate_decision(d)


def test_statistics_requires_evidence():
    with pytest.raises(ValueError):
        p.summarize({a: [[0]*2500 for _ in range(8)] for a in p.ARMS}, evidence_valid=False)
