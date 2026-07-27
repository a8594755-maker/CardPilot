"""Mechanically materialize the registered LG004 trainer from immutable LG003C1.

Only the registered pool-membership seam, identities, and paths are changed.  The
parent is never imported or modified at runtime.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "scripts/alpha_holdem/v5_lg003c1_train_8bf8cedf78b6e8c8fe153802908ed893.py"
OUTPUT = ROOT / "scripts/alpha_holdem/v5_lg004_train_8ef9c64242a75f99bfe04d44de5b643b.py"
PARENT_SHA = "f841144c883d51e66a1d2de889e15303e7339695c8664f81e60208ff77770452"
OLD_TOKEN = "fbd630ab6a689913afc1cee8a63066dd"
OLD_CORRECTION = "8bf8cedf78b6e8c8fe153802908ed893"
TOKEN = "8ef9c64242a75f99bfe04d44de5b643b"
PREREG_SHA = "156b54be70472e9f139672ba5f537a6db39cbea240c2cc21055f679c9f46ae05"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}_anchor_count:{count}")
    return text.replace(old, new)


def main() -> int:
    if sha256(PARENT) != PARENT_SHA:
        raise RuntimeError("parent_hash_mismatch")
    if OUTPUT.exists():
        raise RuntimeError("fresh_output_exists")
    text = PARENT.read_text(encoding="utf-8")
    text = text.replace("LG003", "LG004").replace("lg003", "lg004")
    text = text.replace(OLD_CORRECTION, TOKEN).replace(OLD_TOKEN, TOKEN)
    text = text.replace(
        "525dc9acb2672218f6b09466b3a16d50e8303fa079640b146e58688b239d254d",
        PREREG_SHA,
    )

    constants_start = text.index("LG004_TOKEN = ")
    constants_end = text.index("\n\ndef lg004_assignment_u64", constants_start)
    constants = f"""LG004_TOKEN = '{TOKEN}'
LG004_PREREG_SHA256 = '{PREREG_SHA}'
LG004_ASSIGNMENT_TOKEN = '{OLD_TOKEN}'
LG004_ASSIGNMENT_SEED = 2026072301
LG004_SOURCE_SHA256 = '96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13'
LG004_HISTORICAL_SHA256 = '3bbaf4c6a42d5155964e05bfcef6cce45f484875d34b94f59a6804805b53fe94'
LG004_SNAPSHOT81_SHA256 = 'fd3aec2b32bcc7900eaf255c3ecda8c5cb8dd6339d6ba6551bba07decc91a145'
LG004_SOURCE_ORDER = (109, 115, 120, 129, 103)
LG004_CHECKPOINT_ORDER = (109, 115, 120, 129, 81)
LG004_WEIGHTS = {{
    'treatment_membership': {{81: 0.2, 109: 0.2, 115: 0.2, 120: 0.2, 129: 0.2}},
}}


def lg004_state_dict_sha256(state):
    digest = hashlib.sha256()
    for name in sorted(state):
        tensor = state[name].detach().cpu().contiguous()
        metadata = json.dumps(
            [name, str(tensor.dtype), list(tensor.shape)],
            sort_keys=True, separators=(',', ':'), ensure_ascii=True,
        ).encode('utf-8')
        digest.update(len(metadata).to_bytes(8, 'big'))
        digest.update(metadata)
        digest.update(tensor.numpy().tobytes())
    return digest.hexdigest()
"""
    text = text[:constants_start] + constants + text[constants_end:]
    text = replace_once(
        text,
        "f'LG004_ASSIGNMENT_V1|{LG004_TOKEN}|{LG004_ASSIGNMENT_SEED}|'",
        "f'LG003_ASSIGNMENT_V1|{LG004_ASSIGNMENT_TOKEN}|{LG004_ASSIGNMENT_SEED}|'",
        "assignment_identity",
    )
    text = text.replace("'assignment_rule': 'LG004_ASSIGNMENT_V1'", "'assignment_rule': 'LG003_ASSIGNMENT_V1'")
    text = replace_once(
        text,
        "choices=('none', 'control_uniform', 'treatment_diversity')",
        "choices=('none', 'treatment_membership')",
        "arm_choices",
    )
    text = text.replace(
        "v5_lg004_cleanroom_diversity_league_preregistration_"
        f"{TOKEN}_20260723.json",
        f"v5_lg004_membership_preregistration_{TOKEN}_20260723.json",
    )
    text = text.replace(
        f"v5_lg004c1_{TOKEN}_20260723",
        f"v5_lg004_{TOKEN}_20260723",
    )
    text = replace_once(
        text,
        "    lg004_contract = None\n",
        "    lg004_contract = None\n    lg004_snapshot81 = None\n",
        "snapshot81_scope",
    )

    validation_old = """        checkpoint = torch.load(source_path, map_location='cpu', weights_only=False)
        snapshots = checkpoint.get('pool_snapshots') or []
        ids = tuple(int(row.get('id', -1)) for row in snapshots)
        if (
            int(checkpoint.get('iteration', -1)) != 35051
            or int(checkpoint.get('total_hands', -1)) != 576021901
            or ids != LG004_CHECKPOINT_ORDER
            or 'model' not in checkpoint
            or 'optimizer' not in checkpoint
        ):
            parser.error('LG004 checkpoint payload or frozen pool mismatch')
"""
    validation_new = """        checkpoint = torch.load(source_path, map_location='cpu', weights_only=False)
        source_snapshots = checkpoint.get('pool_snapshots') or []
        source_ids = tuple(int(row.get('id', -1)) for row in source_snapshots)
        if (
            int(checkpoint.get('iteration', -1)) != 35051
            or int(checkpoint.get('total_hands', -1)) != 576021901
            or source_ids != LG004_SOURCE_ORDER
            or 'model' not in checkpoint
            or 'optimizer' not in checkpoint
        ):
            parser.error('LG004 source checkpoint payload or frozen pool mismatch')
        historical_path = (
            workspace / 'models' / 'alpha_holdem_v5_from_zero'
            / 'v5_zero_l6_exp004_pre001_exp002_multienv_rollback_r1_20260708'
            / 'v5_mirror_plateau_second_gate20700_340M_checkpoint.pt'
        ).resolve()
        if sha256_path(historical_path) != LG004_HISTORICAL_SHA256:
            parser.error('LG004 historical container hash mismatch')
        historical = torch.load(historical_path, map_location='cpu', weights_only=False)
        historical_matches = [
            row for row in historical.get('pool_snapshots', [])
            if int(row.get('id', -1)) == 81
        ]
        if len(historical_matches) != 1:
            parser.error('LG004 historical snapshot81 cardinality mismatch')
        lg004_snapshot81 = historical_matches[0]
        source103 = source_snapshots[-1]
        state81 = lg004_snapshot81.get('state_dict') or {}
        state103 = source103.get('state_dict') or {}
        compatible = (
            set(state81) == set(state103)
            and all(
                tuple(state81[key].shape) == tuple(state103[key].shape)
                and state81[key].dtype == state103[key].dtype
                for key in state103
            )
        )
        if (
            int(lg004_snapshot81.get('iteration', -1)) != 18000
            or int(lg004_snapshot81.get('hands', -1)) != 295538136
            or abs(float(lg004_snapshot81.get('selection_loss')) - 3.6118517525455847) > 1e-12
            or lg004_state_dict_sha256(state81) != LG004_SNAPSHOT81_SHA256
            or not compatible
        ):
            parser.error('LG004 snapshot81 identity or tensor compatibility mismatch')
        snapshots = [row for row in source_snapshots if int(row.get('id', -1)) != 103]
        snapshots.append(lg004_snapshot81)
        ids = tuple(int(row.get('id', -1)) for row in snapshots)
        if ids != LG004_CHECKPOINT_ORDER:
            parser.error('LG004 treatment pool construction mismatch')
"""
    text = replace_once(text, validation_old, validation_new, "validation_block")

    contract_old = """            'pool_checkpoint_order': list(LG004_CHECKPOINT_ORDER),
            'assignment_seed': LG004_ASSIGNMENT_SEED,
"""
    contract_new = """            'source_pool_order': list(LG004_SOURCE_ORDER),
            'pool_checkpoint_order': list(LG004_CHECKPOINT_ORDER),
            'removed_member_id': 103,
            'inserted_member_id': 81,
            'inserted_member_state_sha256': LG004_SNAPSHOT81_SHA256,
            'historical_container_sha256': LG004_HISTORICAL_SHA256,
            'assignment_rule': 'LG003_ASSIGNMENT_V1',
            'assignment_token': LG004_ASSIGNMENT_TOKEN,
            'assignment_seed': LG004_ASSIGNMENT_SEED,
"""
    text = replace_once(text, contract_old, contract_new, "contract_block")

    resume_anchor = """        if 'pool_snapshots' in ckpt:
            pool.load_from_checkpoint(
                ckpt.get('pool_snapshots') or [],
                candidate_history=ckpt.get('pool_candidate_history'),
            )
"""
    resume_replacement = resume_anchor + """        if lg004_active:
            if lg004_snapshot81 is None:
                raise RuntimeError('LG004 snapshot81 was not validated')
            pool.snapshots = [
                row for row in pool.snapshots if int(row.get('id', -1)) != 103
            ]
            inserted = dict(lg004_snapshot81)
            inserted['state_dict'] = OpponentPool._clone_state(lg004_snapshot81['state_dict'])
            pool.snapshots.append(inserted)
            if tuple(pool.active_ids()) != LG004_CHECKPOINT_ORDER:
                raise RuntimeError(f'LG004 runtime pool replacement mismatch: {pool.active_ids()}')
"""
    text = replace_once(text, resume_anchor, resume_replacement, "runtime_replacement")

    if "treatment_diversity" in text or "control_uniform" in text:
        raise RuntimeError("obsolete_arm_literal_remains")
    if text.count("LG004_HISTORICAL_SHA256") < 3 or text.count("LG004_SNAPSHOT81_SHA256") < 3:
        raise RuntimeError("membership_contract_not_fully_bound")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("x", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    print(f"LG004_MATERIALIZED {OUTPUT} {sha256(OUTPUT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
