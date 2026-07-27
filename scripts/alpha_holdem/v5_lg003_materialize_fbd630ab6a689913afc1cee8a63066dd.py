#!/usr/bin/env python3
"""Materialize the registered LG003 clean-room trainer without executing it."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TOKEN = "fbd630ab6a689913afc1cee8a63066dd"
PREREG = ROOT / "reports" / f"v5_lg003_cleanroom_diversity_league_preregistration_{TOKEN}_20260723.json"
CURRENT = ROOT / "scripts" / "alpha_holdem" / "train_v5.py"
CLEAN = ROOT / "scripts" / "alpha_holdem" / f"v5_lg003_h11_clean_base_{TOKEN}.py"
TRAINER = ROOT / "scripts" / "alpha_holdem" / f"v5_lg003_train_{TOKEN}.py"

PREREG_SHA256 = "525dc9acb2672218f6b09466b3a16d50e8303fa079640b146e58688b239d254d"
CURRENT_SHA256 = "9d42ff31a57c13ae8afd361b553fe9ea6e086c3e6d0c46328012f39b245b5310"
CLEAN_SHA256 = "7cacc211065ab8494b9bb12c7d8b4ad30abbb303bb29875f9d70b756a52f8ca7"
CLEAN_BYTES = 156892
CUTOFF = "2026-07-15T08:09:10"
SESSION_LOGS = (
    (
        Path(r"C:\Users\a8594\.codex\sessions\2026\07\09\rollout-2026-07-09T16-34-19-019f4896-90db-7dd0-bb9a-8425bb5a37f4.jsonl"),
        "8b8b5fd5377bd229f5286659d043f11df7a8a056dca210042cb02e5396c9cb7a",
    ),
    (
        Path(r"C:\Users\a8594\.codex\sessions\2026\07\22\rollout-2026-07-22T11-31-34-019f8a74-0d12-7a93-b9be-e05798d2c826.jsonl"),
        "dc920b014b74aeef07af644207d87601468ba0143919144bff769ab37a3bd945",
    ),
    (
        Path(r"C:\Users\a8594\.codex\sessions\2026\07\22\rollout-2026-07-22T09-21-58-019f89fd-666d-7923-9bfc-1712eff5c791.jsonl"),
        "97a24c12777d5af7dad88493a75fc1d74390b3708219db289732295f623a69a6",
    ),
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def update_sections(patch: str) -> list[list[str]]:
    lines = patch.splitlines()
    sections: list[list[str]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("*** Update File:") and "train_v5.py" in line:
            end = index + 1
            while end < len(lines):
                candidate = lines[end]
                if candidate.startswith("*** ") and not candidate.startswith("*** End"):
                    break
                end += 1
            sections.append(lines[index + 1 : end])
            index = end
        else:
            index += 1
    return sections


def reverse_section(text: list[str], section: list[str]) -> int:
    starts = [index for index, line in enumerate(section) if line.startswith("@@")]
    applied = 0
    for hunk_index in range(len(starts) - 1, -1, -1):
        start = starts[hunk_index] + 1
        end = starts[hunk_index + 1] if hunk_index + 1 < len(starts) else len(section)
        old: list[str] = []
        new: list[str] = []
        for line in section[start:end]:
            if not line:
                continue
            if line.startswith("*** "):
                break
            if line[0] == " ":
                old.append(line[1:])
                new.append(line[1:])
            elif line[0] == "-":
                old.append(line[1:])
            elif line[0] == "+":
                new.append(line[1:])
        if not new:
            continue
        positions = [
            index
            for index in range(len(text) - len(new) + 1)
            if text[index : index + len(new)] == new
        ]
        if positions:
            position = positions[-1]
            text[position : position + len(new)] = old
            applied += 1
    return applied


def reconstruct_clean_base() -> str:
    if sha256_path(PREREG) != PREREG_SHA256:
        raise RuntimeError("LG003 preregistration hash mismatch")
    if sha256_path(CURRENT) != CURRENT_SHA256:
        raise RuntimeError("censured train_v5.py evidence image changed")
    calls: list[tuple[str, str]] = []
    for path, expected_hash in SESSION_LOGS:
        if sha256_path(path) != expected_hash:
            raise RuntimeError(f"session-log identity mismatch: {path}")
        for raw_line in path.open(encoding="utf-8", errors="replace"):
            try:
                row = json.loads(raw_line)
            except json.JSONDecodeError:
                continue
            timestamp = row.get("timestamp", "")
            payload = row.get("payload", {})
            call_input = payload.get("input") or payload.get("arguments") or ""
            if (
                timestamp < CUTOFF
                or payload.get("type") not in ("custom_tool_call", "function_call")
                or "*** Update File:" not in call_input
                or "train_v5.py" not in call_input
            ):
                continue
            match = re.search(
                r'const\s+patch\s*=\s*("(?:\\.|[^"\\])*"|`[\s\S]*?`)\s*;',
                call_input,
            )
            if not match:
                continue
            literal = match.group(1)
            try:
                patch = json.loads(literal) if literal.startswith('"') else literal[1:-1]
            except json.JSONDecodeError:
                continue
            calls.append((timestamp, patch))

    text = CURRENT.read_text(encoding="utf-8").splitlines()
    applied = 0
    for _, patch in sorted(calls, reverse=True):
        for section in reversed(update_sections(patch)):
            applied += reverse_section(text, section)
    clean = "\n".join(text) + "\n"
    encoded = clean.encode("utf-8")
    if len(encoded) != CLEAN_BYTES or hashlib.sha256(encoded).hexdigest() != CLEAN_SHA256:
        raise RuntimeError("clean H11 reconstruction identity mismatch")
    forbidden = [name for name in ("LG001", "LG002", "H12", "H13", "H14", "H15", "H16", "H17", "H18") if name.lower() in clean.lower()]
    if forbidden:
        raise RuntimeError(f"forbidden post-H11 symbols remain: {forbidden}")
    if applied != 90:
        raise RuntimeError(f"unexpected reverse-hunk count: {applied}")
    return clean


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, observed {count}")
    return source.replace(old, new, 1)


def build_trainer(clean: str) -> str:
    source = clean
    constants = f'''
LG003_TOKEN = {TOKEN!r}
LG003_PREREG_SHA256 = {PREREG_SHA256!r}
LG003_ASSIGNMENT_SEED = 2026072301
LG003_SOURCE_SHA256 = '96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13'
LG003_CHECKPOINT_ORDER = (109, 115, 120, 129, 103)
LG003_WEIGHTS = {{
    'control_uniform': {{103: 0.2, 109: 0.2, 115: 0.2, 120: 0.2, 129: 0.2}},
    'treatment_diversity': {{
        103: 0.151331630996897,
        109: 0.272679451627751,
        115: 0.062503368673781,
        120: 0.325118010944971,
        129: 0.1883675377566,
    }},
}}


def lg003_assignment_u64(absolute_iteration: int) -> int:
    payload = (
        f'LG003_ASSIGNMENT_V1|{{LG003_TOKEN}}|{{LG003_ASSIGNMENT_SEED}}|'
        f'{{int(absolute_iteration)}}'
    )
    return int.from_bytes(hashlib.sha256(payload.encode('utf-8')).digest()[:8], 'big')


def lg003_select_opponent(arm: str, absolute_iteration: int, pool_snapshots):
    if arm not in LG003_WEIGHTS:
        raise ValueError(f'unknown LG003 arm: {{arm}}')
    ids = [int(snapshot.get('id', -1)) for snapshot in pool_snapshots]
    if tuple(ids) != LG003_CHECKPOINT_ORDER or len(set(ids)) != len(ids):
        raise ValueError(f'LG003 frozen pool mismatch: {{ids}}')
    u64 = lg003_assignment_u64(absolute_iteration)
    unit = u64 / float(1 << 64)
    selected_member_id = None
    local_index = HERO_MODEL_ID
    conditional_unit = None
    if unit >= 0.2:
        conditional_unit = (unit - 0.2) / 0.8
        cumulative = 0.0
        for member_id in sorted(LG003_WEIGHTS[arm]):
            cumulative += LG003_WEIGHTS[arm][member_id]
            if conditional_unit < cumulative:
                selected_member_id = member_id
                break
        if selected_member_id is None:
            selected_member_id = max(LG003_WEIGHTS[arm])
        local_index = ids.index(selected_member_id)
    assignment = {{
        'assignment_rule': 'LG003_ASSIGNMENT_V1',
        'assignment_seed': LG003_ASSIGNMENT_SEED,
        'u64': int(u64),
        'unit_interval': unit,
        'conditional_unit_interval': conditional_unit,
        'arm': arm,
        'self_probability': 0.2,
        'conditional_weights_by_member_id': {{
            str(k): v for k, v in sorted(LG003_WEIGHTS[arm].items())
        }},
        'selected_kind': 'self_play' if local_index == HERO_MODEL_ID else 'pool_snapshot',
        'selected_local_index': int(local_index),
        'selected_member_id': selected_member_id,
    }}
    return local_index, assignment


def lg003_enrich_provenance_record(record: dict, assignment: dict) -> dict:
    enriched = dict(record)
    enriched.pop('record_sha256', None)
    enriched['schema_version'] = 'v5.lg003.opponent_assignment_provenance.v1'
    enriched['lg003'] = {{
        'registration_token': LG003_TOKEN,
        'registration_sha256': LG003_PREREG_SHA256,
        **assignment,
    }}
    canonical = json.dumps(
        enriched, sort_keys=True, separators=(',', ':'), ensure_ascii=False,
    )
    enriched['record_sha256'] = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
    return enriched
'''
    source = replace_once(
        source,
        "HERO_MODEL_ID = -1  # request_model_id sentinel for \"use hero model\"\n\n",
        "HERO_MODEL_ID = -1  # request_model_id sentinel for \"use hero model\"\n" + constants + "\n",
        "constants",
    )
    cli = """    parser.add_argument(
        '--lg003-arm',
        choices=('none', 'control_uniform', 'treatment_diversity'),
        default='none',
    )
    parser.add_argument('--lg003-preregistration', default='')
    parser.add_argument('--lg003-preregistration-sha256', default='')
    parser.add_argument('--lg003-contract-probe', action='store_true')
"""
    source = replace_once(
        source,
        "    parser.add_argument('--h11-design-lock-sha256', default='')\n",
        "    parser.add_argument('--h11-design-lock-sha256', default='')\n" + cli,
        "cli",
    )
    source = replace_once(
        source,
        "    args = parser.parse_args()\n",
        "    args = parser.parse_args()\n    lg003_active = args.lg003_arm != 'none'\n",
        "active flag",
    )
    source = replace_once(
        source,
        "        and args.h11_window_arm == 'none'\n        and args.ppo_target_kl != 0.0",
        "        and args.h11_window_arm == 'none'\n        and not lg003_active\n        and args.ppo_target_kl != 0.0",
        "target KL guard",
    )
    source = replace_once(
        source,
        "        and args.h11_window_arm == 'none'\n        and args.h8_value_head_catchup_after_kl_stop",
        "        and args.h11_window_arm == 'none'\n        and not lg003_active\n        and args.h8_value_head_catchup_after_kl_stop",
        "catchup guard",
    )
    validation = f"""    lg003_contract = None
    if args.lg003_contract_probe and not lg003_active:
        parser.error('LG003 contract probe requires an active LG003 arm')
    if lg003_active:
        workspace = Path(__file__).resolve().parents[2]
        expected_prereg = (
            workspace / 'reports'
            / 'v5_lg003_cleanroom_diversity_league_preregistration_{TOKEN}_20260723.json'
        ).resolve()
        supplied_prereg = Path(args.lg003_preregistration)
        if (
            not supplied_prereg.is_absolute()
            or supplied_prereg.resolve() != expected_prereg
            or args.lg003_preregistration_sha256.lower() != LG003_PREREG_SHA256
            or not expected_prereg.is_file()
            or sha256_path(expected_prereg) != LG003_PREREG_SHA256
        ):
            parser.error('LG003 preregistration identity mismatch')
        legacy_arms = (
            args.h2_window_arm, args.h6_window_arm, args.h7_window_arm,
            args.h8_window_arm, args.h9_window_arm, args.h10_window_arm,
            args.h11_window_arm,
        )
        if any(arm != 'none' for arm in legacy_arms) or args.showdown_ev_value_targets:
            parser.error('LG003 forbids every legacy behavior arm')
        exact = {{
            'device': 'cuda', 'workers': 22, 'hands_per_iter': 16384,
            'starting_stack': 200.0, 'env_version': 'v55', 'lr': 0.0003,
            'ppo_epochs': 4, 'ppo_target_kl': 0.03, 'mini_batch_size': 1024,
            'epsilon': 0.0, 'gamma': 0.999, 'entropy_coef': 0.05,
            'entropy_floor': 0.3, 'k_best': 5, 'pool_strategy': 'loss-kbest',
            'pool_history_limit': 200, 'self_play_fraction': 0.2,
            'opponent_assignment': 'per-iteration', 'opponent_groups': 5,
            'rollout_mode': 'multi', 'rollout_envs_per_worker': 16,
            'inference_min_batch_slots': 256, 'inference_batch_deadline_us': 1000.0,
            'worker_seed_base': 73000, 'allin_runout_ev_max_runouts': 200,
            'preflop_action_prior_coef': 0.01, 'postflop_action_prior_coef': 0.02,
            'preflop_sb_open_action_prior_coef': 0.0,
            'preflop_bb_vs_open_action_prior_coef': 0.0,
            'critic_contract': CRITIC_V1, 'value_coef': 0.5,
            'snapshot_every': 200, 'save_interval': 1, 'seed': 20260703,
        }}
        mismatches = {{
            key: (getattr(args, key), expected)
            for key, expected in exact.items()
            if getattr(args, key) != expected
        }}
        if mismatches:
            parser.error(f'LG003 common configuration mismatch: {{mismatches}}')
        if not all((
            args.fixed_training_deal_stream, args.mirror_self_play_deals,
            args.allin_runout_ev, args.h8_value_head_catchup_after_kl_stop,
        )):
            parser.error('LG003 retained behavior flags are incomplete')
        if (
            not args.resume or not args.allow_resume or args.reset_optimizer
            or args.reset_hand_counter or not args.opponent_assignment_provenance_file
            or args.overwrite or args.trace_transitions_file or args.validate_stream
        ):
            parser.error('LG003 resume/output/provenance contract mismatch')
        if args.total_hands not in (581021901, 596021901):
            parser.error('LG003 target hand endpoint is not registered')
        if args.max_runtime_seconds not in (10800.0, 21600.0):
            parser.error('LG003 wall-clock bound is not registered')
        source_path = Path(args.resume)
        canonical_source = (
            workspace / 'models' / 'alpha_holdem_v5_hybrid'
            / 'v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715'
            / 'h11_control_endpoint.pt'
        ).resolve()
        if (
            not source_path.is_absolute()
            or source_path.resolve() != canonical_source
            or sha256_path(source_path) != LG003_SOURCE_SHA256
        ):
            parser.error('LG003 exact source checkpoint mismatch')
        checkpoint = torch.load(source_path, map_location='cpu', weights_only=False)
        snapshots = checkpoint.get('pool_snapshots') or []
        ids = tuple(int(row.get('id', -1)) for row in snapshots)
        if (
            int(checkpoint.get('iteration', -1)) != 35051
            or int(checkpoint.get('total_hands', -1)) != 576021901
            or ids != LG003_CHECKPOINT_ORDER
            or 'model' not in checkpoint
            or 'optimizer' not in checkpoint
        ):
            parser.error('LG003 checkpoint payload or frozen pool mismatch')
        output_root = (
            workspace / 'models' / 'alpha_holdem_v5_hybrid'
            / 'v5_lg003_{TOKEN}_20260723'
        ).resolve()
        for label, raw in (
            ('run-dir', args.run_dir), ('out', args.out),
            ('provenance', args.opponent_assignment_provenance_file),
        ):
            path = Path(raw or '')
            if not path.is_absolute():
                parser.error(f'LG003 {{label}} must be absolute')
            try:
                path.resolve().relative_to(output_root)
            except ValueError:
                parser.error(f'LG003 {{label}} escapes registered root')
        lg003_contract = {{
            'registration_token': LG003_TOKEN,
            'registration_sha256': LG003_PREREG_SHA256,
            'source_checkpoint_sha256': LG003_SOURCE_SHA256,
            'source_iteration': 35051,
            'source_total_hands': 576021901,
            'pool_checkpoint_order': list(LG003_CHECKPOINT_ORDER),
            'assignment_seed': LG003_ASSIGNMENT_SEED,
            'conditional_weights': {{
                str(k): v for k, v in sorted(LG003_WEIGHTS[args.lg003_arm].items())
            }},
            'pool_mutation_disabled': True,
        }}
        if args.lg003_contract_probe:
            run_dir = Path(args.run_dir)
            if run_dir.exists():
                parser.error('LG003 zero-output probe requires absent run directory')
            probe = {{
                'schema_version': 'v5.lg003.contract_probe.v1',
                'status': 'PASS',
                'arm': args.lg003_arm,
                'contract': lg003_contract,
                'selector_samples': [
                    {{
                        'absolute_iteration': absolute_iteration,
                        **lg003_select_opponent(
                            args.lg003_arm, absolute_iteration, snapshots,
                        )[1],
                    }}
                    for absolute_iteration in (35052, 35053, 35054, 35055)
                ],
                'files_written': 0,
                'global_rng_consumption': 0,
                'gpu_initialized': False,
            }}
            print(json.dumps(probe, sort_keys=True, separators=(',', ':')))
            return
"""
    source = replace_once(
        source,
        "    if args.inference_min_batch_slots > args.workers * args.rollout_envs_per_worker:\n",
        validation + "    if args.inference_min_batch_slots > args.workers * args.rollout_envs_per_worker:\n",
        "validation",
    )
    source = replace_once(
        source,
        "            'exp_w1_value_warmup': exp_w1_warmup_state,\n        }\n",
        """            'exp_w1_value_warmup': exp_w1_warmup_state,
            'lg003': (
                {
                    **lg003_contract,
                    'arm': args.lg003_arm,
                    'assignment_provenance_tail_sha256': assignment_provenance_last_sha,
                    'pool_membership_frozen': True,
                }
                if lg003_active
                else None
            ),
        }
""",
        "checkpoint payload",
    )
    source = replace_once(
        source,
        "        group_metadata = None\n        if pool.size() == 0:\n",
        "        group_metadata = None\n        lg003_assignment = None\n        if pool.size() == 0:\n",
        "assignment local",
    )
    source = replace_once(
        source,
        """            if random.random() < args.self_play_fraction:
                assigned_np[:] = -1
            else:
                assigned_np[:] = random.randint(0, pool.size() - 1)
""",
        """            if lg003_active:
                selected_index, lg003_assignment = lg003_select_opponent(
                    args.lg003_arm, int(iteration) + 1, pool.snapshots,
                )
                assigned_np[:] = selected_index
            elif random.random() < args.self_play_fraction:
                assigned_np[:] = -1
            else:
                assigned_np[:] = random.randint(0, pool.size() - 1)
""",
        "assignment selector",
    )
    source = replace_once(
        source,
        """                previous_record_sha256=assignment_provenance_last_sha,
            )
            assignment_provenance_fh.write(
""",
        """                previous_record_sha256=assignment_provenance_last_sha,
            )
            if lg003_active:
                record = lg003_enrich_provenance_record(record, lg003_assignment)
            assignment_provenance_fh.write(
""",
        "provenance",
    )
    source = replace_once(
        source,
        "                if iteration % args.snapshot_every == 0:\n",
        "                if iteration % args.snapshot_every == 0 and not lg003_active:\n",
        "pool freeze",
    )
    compile(source, str(TRAINER), "exec")
    return source


def main() -> None:
    if CLEAN.exists() or TRAINER.exists():
        raise SystemExit("refusing to overwrite LG003 materialized source")
    clean = reconstruct_clean_base()
    trainer = build_trainer(clean)
    CLEAN.write_text(clean, encoding="utf-8", newline="\n")
    TRAINER.write_text(trainer, encoding="utf-8", newline="\n")
    print(
        json.dumps(
            {
                "status": "MATERIALIZED_NO_EXECUTION",
                "clean_path": str(CLEAN),
                "clean_sha256": sha256_path(CLEAN),
                "clean_bytes": CLEAN.stat().st_size,
                "trainer_path": str(TRAINER),
                "trainer_sha256": sha256_path(TRAINER),
                "trainer_bytes": TRAINER.stat().st_size,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
