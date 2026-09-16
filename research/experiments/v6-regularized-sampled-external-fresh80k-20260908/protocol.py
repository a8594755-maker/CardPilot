"""Fixed sampled development calibration. No server requests in this module."""
import importlib.util
import math
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
TEMPLATE = ROOT / 'research/experiments/v6-anchor-recent-external-fresh80k-20260907/pair_protocol.py'
spec = importlib.util.spec_from_file_location('retained_four_policy_statistics', TEMPLATE)
statistics_protocol = importlib.util.module_from_spec(spec)
spec.loader.exec_module(statistics_protocol)
ARMS = ('seed1_parent', 'seed1_regularized', 'seed3_parent', 'seed3_regularized')
EXPORTS = ROOT / 'research/experiments/v6-regularized-sampled-export-qualification-20260908'
MODEL_HASHES = {
    'seed1_parent': 'b372bd4fc5d4f2511decfda188ec39d11f8742a4445d286d1da5456002a5f8ea',
    'seed1_regularized': '0401e53aacdeffe6b9e4308309003d992bf096cb8dfd4a475836132989f48136',
    'seed3_parent': '3614177fee0309ae73c69574db92ca8aeafc5cb1a0adc0b63f84da4b09601860',
    'seed3_regularized': 'c9e036f9b7e833c14a23a903af07af32ec159f4e834f0679a777a6d129fb90be',
}
BRIDGE = 'hunl_v6_physical_legacy_v4_observation_bridge_v1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def schedule():
    result = []
    for wave in range(4):
        for slot in range(2):
            index = wave * 2 + slot + 1
            for arm in ARMS[wave:] + ARMS[:wave]:
                result.append(dict(wave=wave, arm=arm, index=index, hands=2500,
                    policy_seed=202609080100 + ARMS.index(arm) * 100 + index,
                    session_id=f'v6_regularized_sampled_20260908_{arm}_s{index:02d}'))
    return result


def session_command(item, runtime, base=BASE):
    require(item in schedule(), 'unregistered session')
    return [str(Path(runtime) / 'alpha_holdem/play_slumbot_v6_journaled.py'),
        '--model', str(Path(base) / 'frozen' / (item['arm'] + '.pt')),
        '--hands', str(item['hands']), '--seed', str(item['policy_seed']),
        '--session-id', item['session_id'], '--out-dir',
        str(Path(base) / 'sessions' / item['arm'] / f"s{item['index']:02d}"),
        '--device', 'cpu', '--policy-mode', 'sample', '--observation-bridge', 'legacy-v4']


def validate_decision(d):
    """Telemetry guard only; full model/CDF/RNG replay is separately mandatory.

    behavior_action_probability is the selected LEGACY slot's probability;
    behavior_probs aggregate aliased slots onto PHYSICAL actions. They need not
    be equal. Do not invalidate correct sampling by conflating these measures.
    """
    require(d['policy_mode'] == 'sample' and d['temperature'] == 1, 'wrong execution')
    require(d['observation_bridge_contract'] == BRIDGE, 'wrong bridge')
    require(math.isfinite(d['uniform']) and 0 <= d['uniform'] < 1, 'invalid uniform')
    selected = d['selected_action_slot']
    require(type(selected) is int and 0 <= selected < 9, 'invalid selected slot')
    require(d['legal_mask'][selected] == 1, 'illegal selected slot')
    require(d['direct_increment'] == d['v6_action_table'][selected], 'wrong physical action')
    legacy = d['legacy_selected_action_slot']
    require(type(legacy) is int and 0 <= legacy < 9 and d['legacy_legal_mask'][legacy] == 1,
            'invalid legacy selected slot')
    require(d['legacy_action_table'][legacy] == d['direct_increment'], 'wrong legacy action')
    for key in ('model_probs', 'behavior_probs'):
        p = d[key]
        require(len(p) == 9 and all(math.isfinite(x) and 0 <= x <= 1 for x in p), 'invalid probabilities')
        require(math.isclose(sum(p), 1, abs_tol=1e-10), 'unnormalized probabilities')
        require(all(x == 0 or d['legal_mask'][i] == 1 for i, x in enumerate(p)), 'illegal probability mass')
    require(all(math.isclose(a, b, abs_tol=1e-12) for a, b in zip(d['model_probs'], d['behavior_probs'])),
            'behavior distribution differs from frozen model')
    probability = d['behavior_action_probability']
    require(math.isfinite(probability) and 0 < probability <= d['behavior_probs'][selected] + 1e-12,
            'invalid legacy selected probability')


def summarize(groups, *, evidence_valid):
    require(set(groups) == set(ARMS), 'wrong endpoints')
    mapping = dict(zip(ARMS, statistics_protocol.ARMS))
    result = statistics_protocol.summarize_four({mapping[k]: v for k, v in groups.items()},
                                               evidence_valid=evidence_valid)
    # Preserve exact mature statistics with an explicit, lossless label mapping.
    return dict(statistics=result, label_mapping=mapping, development_only=True,
                final_acceptance_hands=0, policy_mode='sample', temperature=1)
