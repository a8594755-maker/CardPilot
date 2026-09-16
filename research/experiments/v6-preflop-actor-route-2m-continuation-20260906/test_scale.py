import ast
import inspect
from pathlib import Path
import sys
import textwrap

import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_scale as run


@pytest.mark.parametrize('seed,arm',run.ORDER)
def test_actual_commands_only_continue_retained_run(seed,arm):
    digest,physical,_ = run.CURRENT[(seed,arm)]
    parent = run.parent_path(seed,arm,3)
    argv = run.training_command(seed,arm,3,parent,physical)
    previous = run.read(parent.parent/'command.json')
    assert run.normalized_training_command(argv) == run.normalized_training_command(previous)
    assert argv[2] == str(run.ctl.WRAPPER)
    assert argv[argv.index('--resume')+1] == str(parent)
    assert argv[argv.index('--total-environment-hands')+1] == str(run.INITIAL_PHYSICAL[seed]+2097152)
    assert '--no-reset-optimizer' in argv and '--preserve-resumed-optimizer-lr' in argv
    assert '--reset-hand-counter' not in argv and '--reset-optimizer' not in argv
    assert ('--preflop-trunk-gradient' in argv) == (arm == 'connected')
    assert argv[argv.index('--deal-attempt-registry')+1] == str(run.BASE/'attempt_registry')


@pytest.mark.parametrize('seed,arm',run.ORDER)
def test_original_common_parent_and_reduced_fixed_eval(seed,arm):
    argv = run.evaluate_command(seed,arm,3)
    assert argv[argv.index('--control')+1] == str(run.PARENTS[seed])
    assert argv[argv.index('--pairs-per-anchor')+1] == '512'
    assert argv[argv.index('--seed')+1] == str(run.EVAL_SEEDS[seed])
    assert argv.count('--anchor') == 4
    assert str(run.directory(seed,arm,3)/'latest.pt') in argv


@pytest.mark.parametrize('flag',['--lr','--seed','--worker-seed-base','--ppo-replay-ratio','--source-policy-kl-coef'])
def test_regimen_changes_not_hidden_by_command_normalization(flag):
    argv = run.training_command(1,'connected',3,run.parent_path(1,'connected',3),11551174)
    bad = list(argv)
    bad[bad.index(flag)+1] = 'CHANGED'
    assert run.normalized_training_command(bad) != run.normalized_training_command(argv)


@pytest.mark.parametrize('cell',[(2,'detached',3),(1,'half',3),(1,'connected',2),(3,'detached',4)])
def test_old_or_unregistered_cell_refused(cell):
    with pytest.raises(ValueError):
        run.directory(*cell)


def test_only_evaluator_counts_changed_in_inherited_method():
    original = ast.parse(textwrap.dedent(inspect.getsource(run.ctl.Controller.evaluate)))
    new = ast.parse(textwrap.dedent(inspect.getsource(run.Controller.evaluate)))
    class Counts(ast.NodeTransformer):
        def visit_Constant(self,node):
            if type(node.value) is int and node.value in {32768,8192,2048,131072}:
                node.value = {32768:8192,8192:2048,2048:512,131072:32768}[node.value]
            return node
    assert ast.dump(Counts().visit(original)) == ast.dump(new)


def test_training_and_accounting_core_inherited_unchanged():
    assert run.Controller.train is run.ctl.Controller.train
    assert run.Controller.tick is run.ctl.Controller.tick
    assert run.ctl.prior.DOSES == run.DOSES == {3:2097152}
    assert run.ctl.BASE == run.BASE
    assert run.ctl.parent_path is run.parent_path
    assert run.execution.logger_update is run.logger
    assert sum(run.INITIAL_PHYSICAL[s]+2097152-run.CURRENT[(s,a)][1] for s,a in run.ORDER) == 4185219


@pytest.mark.parametrize('namespace',['old','parent'])
def test_initial_namespace_reuse_refused(monkeypatch,namespace):
    monkeypatch.setattr(run.ctl.prior,'initial_audit',lambda *args:None)
    monkeypatch.setattr(run.ctl,'route_audit',lambda *args:None)
    monkeypatch.setattr(run.ctl.GRADIENT,'checkpoint_flag',lambda *args:True)
    parent = {'fixed_deal_attempt':{'receipt':{'namespace':'parent'}}}
    initial = {'fixed_deal_attempt':{'receipt':{'namespace':namespace}}}
    with pytest.raises(ValueError,match='namespace'):
        run.initial_gate(parent,initial,{'old'})


def test_preflight_is_not_a_claim_of_bitwise_worker_restore():
    source = Path(run.__file__).read_text(encoding='utf-8')
    assert 'statistical_not_bitwise_worker_continuation' in source
    assert 'earlier_unknown_lineage_tail_hands' in source
    assert run.DOSES.keys() == {3}
    assert len(run.ORDER) == len(set(run.ORDER)) == 4


def test_live_poker_guard(monkeypatch):
    class Process:
        pid = -123
        info = {'cmdline':['python','train_candidate.py']}
    monkeypatch.setattr(run.ctl.psutil,'process_iter',lambda *args:[Process()])
    with pytest.raises(ValueError,match='owner'):
        run.reject_live_poker()

