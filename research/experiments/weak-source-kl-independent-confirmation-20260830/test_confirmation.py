"""Synthetic confirmation contracts; zero actual poker hands."""
import copy
import importlib.util
from pathlib import Path
import sys

import pytest

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
import run_confirmation as run
import finish_confirmation as finish

# Reuse an existing well-defined synthetic raw-cell fixture, not historical games.
spec = importlib.util.spec_from_file_location('parent_synthetic_fixture', run.PARENT/'test_completed_report.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


def doc(label='weak', point=.01):
    digest = next(d for name, _, d in run.CANDIDATES if name == label)
    result = fixture.doc(digest, point=point, pairs=4)
    result['seed'] = run.SEED
    for i, row in enumerate(result['anchors']): row['action_rng']['seed'] = run.SEED+i*1000003
    return result, digest


def test_valid_cell_and_independent_stream():
    cell, digest = doc()
    assert run.SEED == 20260909 and run.PAIRS == 8192
    assert run.validate_cell(cell, {'status': 'COMPLETED'}, digest, pairs=4) == 24
    cell['seed'] = 20260908
    with pytest.raises(ValueError): run.validate_cell(cell, {'status': 'COMPLETED'}, digest, pairs=4)


@pytest.mark.parametrize('bad', ['seed', 'count', 'missing', 'nan', 'bool', 'anchor', 'digest', 'execution', 'ood', 'ci'])
def test_corrupted_evidence_rejected(bad):
    cell, digest = doc()
    execution = {'status': 'COMPLETED'}
    row = cell['anchors'][0]
    if bad == 'seed': row['action_rng']['seed'] += 1
    elif bad == 'count': row['hands'] += 1
    elif bad == 'missing': row['paired_outcomes']['bb_bb_per_hand'].pop()
    elif bad == 'nan': row['paired_outcomes']['sb_bb_per_hand'][0] = float('nan')
    elif bad == 'bool': row['pair_wins'] = True
    elif bad == 'anchor': cell['anchors'].reverse()
    elif bad == 'digest': cell['candidate']['sha256'] = 'wrong'
    elif bad == 'execution': execution['status'] = 'RUNNING'
    elif bad == 'ood': row['anchor_ood_node_rate'] = .9
    else: row['candidate_ci95_bb100'] = 1.
    with pytest.raises(ValueError): run.validate_cell(cell, execution, digest, pairs=4)


def test_adjusted_gate_and_source_guard():
    documents = {name: doc(name, point=.01 if name == 'weak' else 0.)[0] for name, _, _ in run.CANDIDATES}
    result = run.analyze(documents)
    primary, source = result['comparisons']['weak_vs_control'], result['comparisons']['weak_vs_source']
    assert result['replication_passed'] and finish.gate(primary, source)
    changed = copy.deepcopy(primary)
    for row in changed: row['bonferroni_lower'] = -.1
    assert all(row['ci95_lower'] > 0 for row in changed)
    assert not finish.gate(changed, source)
    changed_source = copy.deepcopy(source)
    changed_source[0]['delta_bb100'] = -.01
    assert not finish.gate(primary, changed_source)
    primary[0]['ood_valid'] = False
    assert not finish.gate(primary, source)


def test_parent_checkpoint_identities_are_fixed():
    assert run.CANDIDATES[1][2] == '9bffa0a8628725371d06d1c115de21cdd7e0bc2e45dcf92db140e4796a3fcbeb'
    assert run.CANDIDATES[2][2] == 'a68ac47aad7fa943f0e784e1c14be3d742fac7390a2cd853ba6cb971b429019b'
    assert run.PARENT_ANALYSIS_SHA == '4d789640d9f9e11deaac4d5708aaf42de20db3fef955f0d0cea1db543b560578'
