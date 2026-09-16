from pathlib import Path
import sys

import run_pilot as run


def without_arm(command):
    ignored = {"--run-id", "--run-dir", "--out", "--opponent-assignment-provenance-file"}
    result = []
    index = 0
    while index < len(command):
        if command[index] in ignored:
            index += 2
        elif command[index] in ("--all-policy-heads-only-training", "--flat-sequence-policy-adapter-hidden", "--flat-sequence-adapter-only-training"):
            index += 2 if command[index] == "--flat-sequence-policy-adapter-hidden" else 1
        else:
            result.append(command[index]); index += 1
    return result


def test_arm_commands_are_matched_except_fixed_architecture_scope(tmp_path):
    control = run.training_command("control", tmp_path)
    treatment = run.training_command("treatment", tmp_path)
    assert without_arm(control) == without_arm(treatment)
    assert "--all-policy-heads-only-training" in control
    assert "--flat-sequence-adapter-only-training" in treatment
    assert treatment[treatment.index("--flat-sequence-policy-adapter-hidden") + 1] == "128"


def test_fixed_budgets_and_seeds_are_present(tmp_path):
    for arm in ("control", "treatment"):
        command = run.training_command(arm, tmp_path)
        for flag, expected in (("--total-environment-hands", str(run.TARGET)), ("--seed", "20261033"), ("--worker-seed-base", "2026103300")):
            assert command[command.index(flag) + 1] == expected


def test_gate_requires_both_positive_lower_bounds_and_three_anchors():
    positive = {"ci95": [0.1, 2.0]}
    negative = {"ci95": [-0.1, 2.0]}
    assert run.gate(positive, positive, [1, 1, 1, -1, -1])
    assert not run.gate(negative, positive, [1, 1, 1, 1, 1])
    assert not run.gate(positive, positive, [1, 1, -1, -1, -1])


def test_source_and_five_anchor_inputs_exist():
    assert run.sha(run.SOURCE) == run.SOURCE_SHA
    rows = run.read(run.ANCHORS / "anchor_manifest.json")
    assert len(rows) >= 5 and all(Path(row["path"]).is_file() for row in rows[:5])
