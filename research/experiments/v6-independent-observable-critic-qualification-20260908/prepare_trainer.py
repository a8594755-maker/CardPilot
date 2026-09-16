"""Exclusive mechanical trainer derivation; no changes to parent runtime."""
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
SOURCE = BASE.parent / 'v6-preflop-actor-trunk-route-qualification-20260906/candidate/scripts/alpha_holdem/train_v5.py'
SHA = 'bcce947477fdcf6593b7a88ce6845bf5638ce6698b9462deeecf4133b05472e6'


def prepare():
    raw = SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA:
        raise ValueError('frozen trainer changed')
    text = raw.decode('utf-8').replace('\r\n', '\n')
    changes = [
        ('from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet, CRITIC_V1, CRITIC_V2, count_parameters',
         'from candidate_network import AlphaHoldemNet, CRITIC_V1, CRITIC_V2, count_parameters\nimport resume_contract as observable_resume', 1),
        ('    args = parser.parse_args()',
         "    parser.add_argument('--independent-observable-critic', action='store_true')\n    args = parser.parse_args()\n    observable_resume.validate_config(vars(args))", 1),
        ("        ckpt = torch.load(args.resume, map_location=device, weights_only=False)",
         "        ckpt = torch.load(args.resume, map_location=device, weights_only=False)\n        observable_resume.before_load(model, optimizer, ckpt, vars(args))", 1),
        ("                optimizer.load_state_dict(ckpt['optimizer'])",
         "                optimizer.load_state_dict(ckpt['optimizer'])\n                observable_resume.after_load(model, optimizer, ckpt, vars(args))", 1),
        ("'model': model.state_dict(),",
         "'observable_critic_contract': (observable_resume.VERSION if hasattr(model, 'observable_value_encoder') else None),\n            'model': model.state_dict(),", 2),
        ('        reference_policy = copy.deepcopy(model).to(device)',
         '        reference_policy = observable_resume.strip_reference_encoder(copy.deepcopy(model)).to(device)', 1),
        ('            m.load_state_dict(snapshot_state)',
         '            observable_resume.attach_snapshot(m, snapshot_state)\n            m.load_state_dict(snapshot_state)', 1),
    ]
    for old, new, count in changes:
        if text.count(old) != count:
            raise ValueError('unexpected replacement count: ' + old)
        text = text.replace(old, new)
    compile(text, str(BASE / 'candidate_train.py'), 'exec')
    data = text.encode('utf-8')
    target = BASE / 'candidate_train.py'
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError('preserve existing different candidate')
    else:
        with target.open('xb') as handle:
            handle.write(data)
    print(json.dumps({'source_sha256': SHA, 'candidate_sha256': hashlib.sha256(data).hexdigest(),
                      'replacement_sites': sum(c for _, _, c in changes)}))
    return target


if __name__ == '__main__':
    prepare()
