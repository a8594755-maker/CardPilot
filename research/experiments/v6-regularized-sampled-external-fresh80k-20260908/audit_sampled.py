"""Use exact legacy-slot model replay for sampled legacy bridge sessions.

The original native physical-slot CDF audit remains unchanged for other routes.
No model-less sampled bridge validation is allowed. This wrapper changes evidence
checking only, not policy inference or journal generation.
"""
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
# The controller must set CARDPILOT runtime import location via PYTHONPATH when
# frozen; source fallback is only for offline qualification before freezing.
if not any((Path(p) / 'alpha_holdem').is_dir() for p in sys.path if p):
    sys.path.insert(0, str(ROOT / 'scripts'))
from alpha_holdem import audit_slumbot_v6_session as original
from alpha_holdem.legacy_observation_bridge_v6 import external_decision as legacy_decision
from alpha_holdem.legacy_observation_bridge_v6 import BRIDGE_CONTRACT

native_validate = original.validate_decision


def validate_decision(row, response, rng, model, policy_mode,
                      decision_fn=original.external_decision,
                      session_policy_state=None, stateful_decision_fn=None):
    # Select by the configured callable, never by untrusted evidence metadata.
    if policy_mode != 'sample' or decision_fn is not legacy_decision:
        return native_validate(row, response, rng, model, policy_mode, decision_fn,
                               session_policy_state, stateful_decision_fn)
    original.need(model is not None and stateful_decision_fn is None, 'Exact legacy model replay required')
    original.need(isinstance(row, dict) and row.get('response') == response, 'Decision context mismatch')
    uniform = rng.random()
    original.need(row.get('uniform') == uniform, 'Policy RNG stream mismatch')
    action, expected = legacy_decision(model, response, uniform=uniform, device='cpu', policy_mode='sample')
    original.need(expected['observation_bridge_contract'] == BRIDGE_CONTRACT and
                  expected['policy_contract'] == original.METADATA['policy_contract'], 'Wrong frozen contract')
    original.need(all(row.get(key) == value for key, value in expected.items()), 'Frozen legacy model decision replay mismatch')
    state = original.from_external(response['action'], response['hole_cards'], response['board'], response['client_pos'])
    mask, table = original.action_table(state)
    slot = row['selected_action_slot']
    original.need(row['legal_mask'] == mask.tolist() and row['action_table'] == table and
                  type(slot) is int and 0 <= slot < 9 and mask[slot] == 1 and
                  action == row['direct_increment'] == table[slot], 'Physical action mismatch')


original.validate_decision = validate_decision

if __name__ == '__main__':
    original.main()
