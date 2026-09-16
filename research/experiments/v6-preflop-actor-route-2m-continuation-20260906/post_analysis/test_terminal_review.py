import ast
import copy
import gzip
import inspect
import json
from pathlib import Path
import random
import sys
import textwrap

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import terminal_review as r


def write_json(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value),encoding='utf-8')


def terminal_fixture(base):
    write_json(base/'ownership.json',r.EXPECTED_OWNER)
    write_json(base/'controller_result.json',{'phase':'FIXED_2M_COMPLETE_NEEDS_RESEARCH_REVIEW'})
    for index in range(8):
        folder = base/f'job{index}'
        write_json(folder/'process.json',{'pid':100+index,'create_time':float(index)})
        write_json(folder/'termination.json',{'exit_code':0,'observer_errors':[],
                   'remaining_observed_child_pids':[],'observed_children':{'200':2.}})


def test_guard_accepts_only_terminal_fixed_jobs(tmp_path,monkeypatch):
    terminal_fixture(tmp_path)
    monkeypatch.setattr(r,'live',lambda *args:False)
    assert r.terminal_guard(tmp_path) == {'ready':True,'jobs':8}


@pytest.mark.parametrize('corruption',['owner','live_owner','error','phase','missing','exit','observer','live_job','live_worker'])
def test_bad_boundary_refused_without_report(tmp_path,monkeypatch,corruption):
    terminal_fixture(tmp_path)
    monkeypatch.setattr(r,'live',lambda *args:False)
    if corruption == 'owner':
        write_json(tmp_path/'ownership.json',{'pid':29304,'create_time':1.})
    elif corruption == 'live_owner':
        monkeypatch.setattr(r,'live',lambda pid,*args:int(pid) == 29304)
    elif corruption == 'error':
        write_json(tmp_path/'controller_error.json',{'preserved':True})
    elif corruption == 'phase':
        write_json(tmp_path/'controller_result.json',{'phase':'SAFE_BOUNDARY_NEEDS_REVIEW'})
    elif corruption == 'missing':
        (tmp_path/'job7/termination.json').unlink()
    elif corruption in ('exit','observer'):
        path = tmp_path/'job0/termination.json'
        value = r.read(path)
        value['exit_code' if corruption == 'exit' else 'observer_errors'] = 1 if corruption == 'exit' else ['error']
        write_json(path,value)
    else:
        monkeypatch.setattr(r,'live',lambda pid,*args:int(pid) == (100 if corruption == 'live_job' else 200))
    with pytest.raises(ValueError):
        r.terminal_guard(tmp_path)
    assert not (tmp_path/'post_terminal_review.json').exists()


def test_raw_parser_only_changes_expected_cardinality():
    previous = ast.parse(textwrap.dedent(inspect.getsource(r.old.old.raw_map)))
    current = ast.parse(textwrap.dedent(inspect.getsource(r.raw_map)))
    class Count(ast.NodeTransformer):
        def visit_Constant(self,node):
            if node.value == 8192:
                node.value = 2048
            return node
    assert ast.dump(Count().visit(previous)) == ast.dump(current)


def test_stage_only_changes_registered_dose_and_seed_binding():
    previous = ast.parse(textwrap.dedent(inspect.getsource(r.old.review_stage)))
    current = ast.parse(textwrap.dedent(inspect.getsource(r.review_stage)))
    class Binding(ast.NodeTransformer):
        def visit_Constant(self,node):
            if type(node.value) is int and node.value in {131072,32768,2048}:
                node.value = {131072:32768,32768:8192,2048:512}[node.value]
            return node
        def visit_BinOp(self,node):
            if ast.unparse(node) == '20264200 + seed * 10 + stage':
                return ast.parse('EVAL_SEEDS[seed]',mode='eval').body
            return self.generic_visit(node)
    assert ast.dump(Binding().visit(previous)) == ast.dump(current)


def raw_rows():
    rng = random.Random(19037)
    rows = []
    for index in range(2048):
        deck = list(range(52))
        rng.shuffle(deck)
        rows.append({'anchor':'abcd'[index//512],'anchor_seed':10+index//512,
            'pair_index':index%512,'deck':deck,'control_rewards_bb':[1.,-1.],
            'treatment_rewards_bb':[2.,-2.],'control_pair_mean_bb':0.,
            'treatment_pair_mean_bb':0.,'treatment_minus_control_rewards_bb':[1.,-1.],
            'treatment_minus_control_pair_mean_bb':0.})
    return rows


@pytest.mark.parametrize('corruption',[None,'duplicate','missing','payout'])
def test_reduced_parser_validates_actual_synthetic_rows(tmp_path,corruption):
    rows = raw_rows()
    if corruption == 'duplicate':
        rows[-1] = copy.deepcopy(rows[0])
    elif corruption == 'missing':
        rows.pop()
    elif corruption == 'payout':
        rows[0]['treatment_rewards_bb'][0] = 201.
    path = tmp_path/'raw.gz'
    with gzip.open(path,'wt',encoding='utf-8') as out:
        for row in rows:
            out.write(json.dumps(row)+'\n')
    if corruption:
        with pytest.raises(ValueError):
            r.raw_map(path)
    else:
        assert len(r.raw_map(path)) == 2048


def test_state_and_statistics_helpers_are_reused():
    for name in ('compare_arms','counter_deltas','adam_steps','gradient_route','training_health'):
        assert getattr(r,name) is getattr(r.old,name)
    assert r.DOSES == {3:2097152}
    assert r.EVAL_SEEDS == {1:20264411,3:20264431}
    source = inspect.getsource(r.main)
    assert "len(decks) == 4096" in source
    assert "counts['evaluation_hands'] += 32768" in source
    assert "namespace not in contract['known_attempt_namespaces']" in source
    assert "'earlier_unknown_lineage_tail_hands': None" in source

