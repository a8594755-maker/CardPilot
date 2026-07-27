# V5 Checkpoint Archive Continuation Fix - 2026-07-07

## Scope

Monitoring/archive fix only. No trainer weights, trainer flags, environment
semantics, policy mode, or Slumbot evaluation policy were changed.

Active run:

- run_id: `v5_zero_l6_exp004_pre001_r1_20260707`
- trainer PID: `58680` (left running)
- continuation parent checkpoint: `models/alpha_holdem_v5_from_zero/v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1/latest.pt`
- parent checkpoint hands: `180,491,565`

## Problem

The checkpoint archive watcher treated a continuation run like a fresh run. Since
the EXP-004 child run resumed from `180,491,565` hands, it immediately copied the
same `iter11000 / 180M` checkpoint under child-run milestone names:

- `v5_zero_l6_exp004_pre001_r1_20260707_50M_iter11000_180M.pt/json`
- `v5_zero_l6_exp004_pre001_r1_20260707_100M_iter11000_180M.pt/json`

Those names incorrectly imply the child run independently reached 50M and 100M
milestones.

## Fix

Patched:

- `scripts/alpha_holdem/v5_checkpoint_archive_watch.py`

New behavior:

- Reads `run_manifest.json` for `lineage_parent_checkpoint` / `config.resume`.
- If a milestone was already reached by the parent checkpoint, marks it
  `INHERITED_PARENT`.
- Does not create child-run archive files for inherited milestones unless
  `--force` is passed.
- Keeps inherited milestone details in `checkpoint_archive_status.json` so the
  audit trail remains explicit.

## Artifact Handling

The mislabeled files were preserved, not deleted. They were moved to:

`models/alpha_holdem_v5_from_zero/v5_zero_l6_exp004_pre001_r1_20260707/milestone_archives/quarantine_mislabeled_20260707/`

Files moved:

- `v5_zero_l6_exp004_pre001_r1_20260707_50M_iter11000_180M.pt`
- `v5_zero_l6_exp004_pre001_r1_20260707_50M_iter11000_180M.json`
- `v5_zero_l6_exp004_pre001_r1_20260707_100M_iter11000_180M.pt`
- `v5_zero_l6_exp004_pre001_r1_20260707_100M_iter11000_180M.json`

The `milestone_archives` root now has no 50M/100M child-run archive files.

## Validation

Completed:

- `python -m py_compile scripts\alpha_holdem\v5_checkpoint_archive_watch.py`: PASS.
- No dedicated `test_v5_checkpoint_archive_watch.py` exists.
- One-shot validation:
  - command: `python -u scripts\alpha_holdem\v5_checkpoint_archive_watch.py --run-dir <exp004_run_dir> --status-json <run_dir>\checkpoint_archive_fix_validation_status.json --log <run_dir>\checkpoint_archive_fix_validation.log --once`
  - `50M`: `INHERITED_PARENT`
  - `100M`: `INHERITED_PARENT`
  - `250M`: `PENDING`
  - parent_hands: `180,491,565`

Persistent watcher restart:

- stopped old checkpoint archive watcher PID `52108`
- restarted patched watcher PID `23388`
- priority: `BelowNormal`
- status: `50M/100M INHERITED_PARENT`, `250M PENDING`
- stderr: empty

## Next Expected Archive

The next real child-run archive should be created at `250,000,000` checkpoint
hands, not at inherited 50M/100M milestones.
