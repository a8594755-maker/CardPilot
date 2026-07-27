#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--prereg', required=True)
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    prereg_path = Path(a.prereg).resolve()
    p = json.loads(prereg_path.read_text(encoding='utf-8'))
    errors: list[str] = []
    checks: dict[str, bool] = {}
    def check(name: str, ok: bool, error: str) -> None:
        checks[name] = bool(ok)
        if not ok: errors.append(error)
    check('schema', p.get('schema_version') == 'v5.hybrid.h2.preregistration.v2', 'schema mismatch')
    check('immutable_status', p.get('immutable') is True and p.get('status') == 'REGISTERED_NO_LAUNCH', 'not immutable registered-no-launch')
    base = p.get('complete_contract', {})
    base_path = Path(base.get('base_path', ''))
    check('base_exists_hash', base_path.is_file() and sha(base_path) == base.get('base_sha256'), 'incorporated v1 hash mismatch')
    sup = p.get('superseding_fields', {})
    bindings = {
      ROOT/'scripts/alpha_holdem/train_v5.py': sup.get('code_bindings.scripts/alpha_holdem/train_v5.py'),
      Path(sup.get('frozen_prerequisites.implementation_audit.path', '')): sup.get('frozen_prerequisites.implementation_audit.sha256'),
    }
    check('bound_files', all(path.is_file() and sha(path) == expected for path, expected in bindings.items()), 'bound file hash mismatch')
    impl = json.loads(next(path for path in bindings if path.name.startswith('v5_hybrid_h2_implementation_audit')).read_text(encoding='utf-8'))
    check('implementation_pass', impl.get('overall') == 'PASS_IMPLEMENTATION_PREREG_READY', 'implementation audit not PASS')
    check('actor_identity', impl.get('actor_identity', {}).get('max_abs_actor_logits_delta') == 0.0, 'actor identity delta nonzero')
    base_json = json.loads(base_path.read_text(encoding='utf-8')) if base_path.is_file() else {}
    check('source_identity', base_json.get('source', {}).get('sha256') == 'bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e', 'source mismatch')
    check('single_variable', base_json.get('single_variable', {}).get('one_behavior_change') is True, 'single variable missing')
    mirror = base_json.get('registered_measurements', {}).get('internal_mirror', {})
    check('mirror_fixed40k', mirror.get('common_deal_pairs') == 40000 and mirror.get('adaptive_extension_allowed') is False, 'mirror is not fixed40k')
    check('zero_official', base_json.get('authority', {}).get('official_slumbot_hands') == 0, 'official hands not zero')
    check('terminal_rules', all(base_json.get('terminal_rule', {}).get(k) for k in ('pass','fail','inconclusive')), 'terminal rule incomplete')
    added = p.get('added_fail_closed_arm_identity', {})
    check('arm_hash_guards', len(added.get('required_cli', [])) == 5 and len(added.get('validation', [])) >= 5, 'arm hash guards incomplete')
    result = {
      'schema_version': 'v5.hybrid.h2.preregistration_audit.v1',
      'checked_at': datetime.now(timezone.utc).isoformat(),
      'preregistration_path': str(prereg_path),
      'preregistration_sha256': sha(prereg_path),
      'checks': checks,
      'errors': errors,
      'overall': 'PASS_IMMUTABLE_H2_PREREGISTRATION' if not errors else 'FAIL_CLOSED',
      'launch_authority': 'NONE_DESIGN_LOCK_PREFLIGHT_REARM_REQUIRED',
      'official_hands_authorized': 0,
    }
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2

if __name__ == '__main__':
    raise SystemExit(main())
