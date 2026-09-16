"""Synthetic confirmation contracts; zero actual poker hands."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
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


def doc(label='full', point=.01):
    digest = next(d for name, _, d in run.CANDIDATES if name == label)
    result = fixture.doc(digest, point=point, pairs=4)
    result['seed'] = run.SEED
    for i, row in enumerate(result['anchors']): row['action_rng']['seed'] = run.SEED+i*1000003
    return result, digest


def test_valid_cell_and_independent_stream():
    cell, digest = doc()
    assert run.SEED == 20260913 and run.PAIRS == 8192
    assert run.validate_cell(cell, {'status': 'COMPLETED'}, digest, pairs=4) == 32
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
    documents = {name: doc(name, point=.01 if name == 'full' else 0.)[0] for name, _, _ in run.CANDIDATES}
    result = run.analyze(documents)
    primary, source = result['comparisons']['full_vs_heads'], result['comparisons']['full_vs_source']
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
    assert run.CANDIDATES[1][2] == 'ebfc850cb8ed92c07103bbb92a8b473433a63c6df173c0f002741c560b84e63b'
    assert run.CANDIDATES[2][2] == 'ff2b9e6fe188ac89aa3ff4b632b70a195a46e8e6a73f1b94a75fcfbbf543c17e'
    assert run.PARENT_ANALYSIS_SHA == '6604dc6f9b827b475c15e8e41e49b20740de974c35b071dc0e65aa623a9df690'


def test_four_anchor_replication_gate_contract():
    documents = {name: doc(name, point=.01 if name == 'full' else 0.)[0] for name, _, _ in run.CANDIDATES}
    result = run.analyze(documents)
    primary = result['comparisons']['full_vs_heads']
    source = result['comparisons']['full_vs_source']
    assert len(primary) == 4 and run.PAIRS*8*len(run.CANDIDATES) == 196608
    only_cfr = copy.deepcopy(primary)
    for row in only_cfr:
        row['bonferroni_lower'] = .1 if row['anchor'] == 'corrected_cfr96' else -.1
    assert not run.admission(only_cfr, source) and not finish.gate(only_cfr, source)
    only_training = copy.deepcopy(primary)
    for row in only_training:
        row['bonferroni_lower'] = .1 if row['anchor'] in ('slumbot_free', 'corrected_cfr96') else -.1
    assert not run.admission(only_training, source) and not finish.gate(only_training, source)
    assert result['parent_discovery_hands_excluded'] == 163840


def test_actual_paired_tool_schema_with_synthetic_raw_evidence(tmp_path):
    control, _ = doc('heads', point=0.)
    treatment, _ = doc('full', point=.01)
    first, second, output = [tmp_path/name for name in ['heads.json', 'full.json', 'paired.json']]
    first.write_text(json.dumps(control))
    second.write_text(json.dumps(treatment))
    subprocess.run([sys.executable, str(run.ROOT/'scripts/alpha_holdem/paired_mirror_treatment_delta.py'),
        '--control', str(first), '--treatment', str(second), '--out', str(output)], check=True, capture_output=True)
    stored = json.loads(output.read_text())
    rows = run.compare(control, treatment)
    assert 'control' in stored and 'heads' not in stored
    run.validate_paired_output(stored, run.sha(first), run.sha(second), rows)
    for bad in ['hash', 'delta', 'ci', 'duplicate', 'boolean']:
        changed = copy.deepcopy(stored)
        if bad == 'hash': changed['control']['sha256'] = 'wrong'
        elif bad == 'delta': changed['anchors'][0]['treatment_minus_control_bb100'] += 1.
        elif bad == 'ci': changed['anchors'][0]['paired_ci95_bb100'] += 1.
        elif bad == 'duplicate': changed['anchors'][1] = copy.deepcopy(changed['anchors'][0])
        else: changed['anchors'][0]['paired_ci95_bb100'] = False
        with pytest.raises(ValueError):
            run.validate_paired_output(changed, run.sha(first), run.sha(second), rows)
