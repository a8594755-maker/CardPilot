import copy
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location('pool_qualified_runner', Path(__file__).with_name('run_pool_qualified_evaluation.py'))
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def proofs():
    failed = [{'dynamic_pool_healthy'},
              {'dynamic_pool_healthy', 'corrected_legacy_contract_bound', 'physical_accounting_exact', 'resume_controls_exact'},
              {'dynamic_pool_healthy', 'corrected_legacy_contract_bound'}]
    original = {'runs': [], 'session_independence': {'unique': True}}
    pool = {'passed': True, 'runs': []}
    mechanics = {'posthoc_observed_mechanics_passed': True, 'runs': []}
    for i, keys in enumerate(failed, 1):
        name, digest = f'seed{i}', str(i) * 64
        original['runs'].append({'name': name, 'gates': dict(healthy=True, **{key: False for key in keys}),
                                 'hashes': {'checkpoint': digest}})
        pool['runs'].append({'name': name, 'passed': True, 'checkpoint_sha256': digest})
        mechanics['runs'].append({'name': name, 'posthoc_observed_mechanics_passed': True,
            'generic_audit': {'hashes': {'checkpoint': digest}},
            'segments': [{'passed': True, 'gates': {'exact': True}} for _ in range(3 if i == 2 else 1)]})
    return original, pool, mechanics


def test_only_qualified_observed_failures_are_accepted_without_mutation():
    values = proofs()
    original = copy.deepcopy(values)
    runner.validate_proofs(*values)
    assert values == original


@pytest.mark.parametrize('mutation', ['extra_failure', 'rewritten_original', 'bad_pool', 'bad_endpoint',
                                    'hash', 'missing_seed', 'segment', 'empty_segments', 'independence'])
def test_unrelated_or_unqualified_evidence_stops(mutation):
    original, pool, mechanics = proofs()
    if mutation == 'extra_failure':
        original['runs'][0]['gates']['weights'] = False
    elif mutation == 'rewritten_original':
        original['runs'][0]['gates']['dynamic_pool_healthy'] = True
    elif mutation == 'bad_pool':
        pool['passed'] = False
    elif mutation == 'bad_endpoint':
        mechanics['runs'][0]['posthoc_observed_mechanics_passed'] = False
    elif mutation == 'hash':
        pool['runs'][0]['checkpoint_sha256'] = 'f' * 64
    elif mutation == 'missing_seed':
        pool['runs'].pop()
    elif mutation == 'segment':
        mechanics['runs'][1]['segments'][1]['gates']['exact'] = False
    elif mutation == 'empty_segments':
        mechanics['runs'][1]['segments'] = []
    else:
        original['session_independence']['unique'] = False
    with pytest.raises(ValueError):
        runner.validate_proofs(original, pool, mechanics)


def test_original_evaluation_budget_and_seed_commands_are_reused():
    for seed in (1, 2, 3):
        argv = runner.old.eval_argv(seed)
        assert str(20263280 + seed) in argv
        assert '2048' in argv
        assert f'eval_seed{seed}' in argv[-1]
