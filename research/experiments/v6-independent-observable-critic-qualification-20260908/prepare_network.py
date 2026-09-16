"""Mechanical, hash-bound derivation; never edits the frozen source."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parent / 'v6-preflop-actor-trunk-route-qualification-20260906/candidate/scripts/alpha_holdem/network_hybrid_h1.py'
SOURCE_SHA = '07350adfc79db5e81d5d978751492aad443aa72d493ff4f9c3cec5774c2840f8'
OLD = '        value_input = h.detach() if self.critic_contract == CRITIC_V2 else h\n'
NEW = '''        if hasattr(self, 'observable_value_encoder'):
            if critic_private_info is not None or return_action_q:
                raise ValueError('independent observable critic forbids privileged/Q routes')
            value_input = self.observable_value_encoder(card_info, action_info, extra_info)
        else:
            value_input = h.detach() if self.critic_contract == CRITIC_V2 else h
'''


def prepare():
    raw = SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise ValueError('frozen hybrid source changed')
    text = raw.decode('utf-8').replace('\r\n', '\n')
    if text.count(OLD) != 1:
        raise ValueError('ambiguous value route')
    candidate = text.replace(OLD, NEW).encode('utf-8')
    target = BASE / 'candidate_network.py'
    if target.exists():
        if target.read_bytes() != candidate:
            raise ValueError('existing candidate differs; preserve and investigate')
    else:
        with target.open('xb') as handle:
            handle.write(candidate)
    result = {'source': str(SOURCE), 'source_sha256': SOURCE_SHA,
              'candidate_sha256': hashlib.sha256(candidate).hexdigest(),
              'exact_replacements': 1, 'training_hands': 0}
    print(json.dumps(result))
    return target


if __name__ == '__main__':
    prepare()
