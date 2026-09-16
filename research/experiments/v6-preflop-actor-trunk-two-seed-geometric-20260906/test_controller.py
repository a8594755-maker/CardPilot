import ast
import copy
from pathlib import Path
import subprocess
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parent))
import run_actor_control as run


@pytest.mark.parametrize('seed',[1,3])
@pytest.mark.parametrize('stage',[1,2])
def test_only_route_differs_in_matched_commands(seed,stage):
    commands = [run.training_command(seed,arm,stage,'parent.pt',run.INITIAL_PHYSICAL[seed]) for arm in ('detached','connected')]
    assert '--preflop-trunk-gradient' not in commands[0]
    assert commands[1].count('--preflop-trunk-gradient')==1
    commands[1].remove('--preflop-trunk-gradient')
    for argv in commands:
        for flag in ('--run-dir','--out','--opponent-assignment-provenance-file'):
            argv[argv.index(flag)+1]='CELL'
        assert argv[2]==str(run.WRAPPER)
        assert '--all-policy-heads-only-training' not in argv
        assert '--no-reset-optimizer' in argv and '--preserve-resumed-optimizer-lr' in argv
        assert '--reset-hand-counter' not in argv and '--reset-optimizer' not in argv
        assert argv[argv.index('--total-environment-hands')+1]==str(run.INITIAL_PHYSICAL[seed]+run.DOSES[stage])
        assert argv[argv.index('--source-policy-reference-refresh-updates')+1]=='0'
        assert argv[argv.index('--mini-batch-size')+1]=='16384'
        assert '--managed-deal-attempts' in argv
    assert commands[0]==commands[1]


@pytest.mark.parametrize('seed',[1,3])
@pytest.mark.parametrize('arm',['detached','connected'])
def test_parent_and_resume_paths(seed,arm):
    first=run.parent_path(seed,arm,1)
    assert first== (run.PARENTS[seed] if arm=='detached' else run.QUAL/f'seed{seed}_connected_unstepped.pt')
    assert run.parent_path(seed,arm,2)==run.directory(seed,arm,1)/'latest.pt'


@pytest.mark.parametrize('seed',[1,3])
@pytest.mark.parametrize('stage',[1,2])
def test_same_fresh_decks_and_original_parent(seed,stage):
    commands=[run.evaluate_command(seed,arm,stage) for arm in ('detached','connected')]
    for argv in commands:
        assert argv[argv.index('--control')+1]==str(run.PARENTS[seed])
        assert argv[argv.index('--pairs-per-anchor')+1]=='2048'
        assert argv[argv.index('--seed')+1]==str(20264200+seed*10+stage)
        for flag in ('--treatment','--out-dir'):
            argv[argv.index(flag)+1]='CELL'
    assert commands[0]==commands[1]


@pytest.mark.parametrize('cell',[(0,'detached',1),(1,'half',1),(3,'connected',3),(2,'connected',2)])
def test_unknown_cells_refused(cell):
    with pytest.raises(ValueError):
        run.directory(*cell)


@pytest.mark.parametrize('connected',[False,True])
def test_route_audit_preserves_origin(connected):
    flag=run.GRADIENT.FLAG
    origin={'source_checkpoint_sha256':'0'*64} if connected else None
    config={flag:connected,'separate_preflop_head':True,'preflop_teacher_coef':0.,'hero_preflop_strategy':'model'}
    parent={flag:connected,'config':config,run.GRADIENT.ORIGIN:origin}
    run.route_audit(copy.deepcopy(parent),connected,parent)
    bad=copy.deepcopy(parent)
    bad[flag]=not connected
    with pytest.raises(ValueError):
        run.route_audit(bad,connected,parent)


def test_migration_loss_refused():
    flag=run.GRADIENT.FLAG
    parent={'config':{flag:True,'separate_preflop_head':True},flag:True,run.GRADIENT.ORIGIN:{'source':'frozen'}}
    final=copy.deepcopy(parent)
    final[run.GRADIENT.ORIGIN]=None
    with pytest.raises(ValueError,match='provenance'):
        run.route_audit(final,True,parent)


@pytest.mark.parametrize('gate_side',['contrast','endpoint'])
def test_severe_gate_reuses_existing_breadth_rule(monkeypatch,gate_side):
    marker={'bad':True}
    monkeypatch.setattr(run.evidence,'broad_collapse',lambda value:value.get('bad',False))
    assert run.collapse_gate(marker if gate_side=='contrast' else {}, {'a':marker if gate_side=='endpoint' else {}})
    assert not run.collapse_gate({}, {'a':{}})


def test_reused_execution_and_full_scope_inspector():
    assert run.Controller.execute is run.execution.Controller.execute
    assert run.prior.INITIAL_PHYSICAL==run.INITIAL_PHYSICAL and run.prior.DOSES==run.DOSES
    tree=ast.parse(Path(run.__file__).read_text(encoding='utf-8'))
    calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call)]
    inspect_calls=[n for n in calls if ast.unparse(n.func)=='prior.inspect_training']
    assert len(inspect_calls)==1 and ast.literal_eval(inspect_calls[0].args[5])=='full'
    assert len([n for n in calls if ast.unparse(n.func)=='route_audit'])==3


def test_frozen_wrapper_actual_cli():
    process=subprocess.run([sys.executable,'-B',str(run.WRAPPER),'--help'],cwd=run.ROOT,capture_output=True,text=True,timeout=45)
    assert process.returncode==0,process.stderr
    assert '--preflop-trunk-gradient' in process.stdout
    assert str(run.QUAL/'candidate').replace('\\','\\\\') in process.stdout
