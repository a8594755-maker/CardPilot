import copy
import random

import pytest

from scripts.alpha_holdem.fixed_deal_resume_integrity import (
    single_env_intervals, summarize_overlap, validate_resume_start,
)


def attempt(label="a", start=100, counts=(10, 20), seed=700):
    return {"label": label, "config": {
        "fixed_training_deal_stream": True, "rollout_mode": "single",
        "worker_seed_base": seed, "workers": 2,
        "fixed_training_deal_start_index": start,
    }, "accounting": {"session_completed_hands": sum(counts),
                       "session_worker_counts": [
                           {"worker_id": w, "completed_hands": n}
                           for w, n in enumerate(counts)]}}


def test_same_start_replays_prefix_without_changing_physical_count():
    result = summarize_overlap([attempt(), attempt("b", counts=(3, 4)),
                                attempt("c", counts=(7, 9))])
    assert result["executed_hands"] == 53
    assert result["unique_evidenced_deal_identities"] == 30
    assert result["repeated_deal_exposures"] == 23
    assert not result["physical_counter_correction_required"]


def test_partial_overlap_and_disjoint_workers():
    result = summarize_overlap([attempt(), attempt("b", start=115),
                                attempt("c", seed=900)])
    assert result["executed_hands"] == 90
    assert result["repeated_deal_exposures"] == 5


def test_resume_checks_all_attempts_not_just_latest():
    previous = [attempt(counts=(100, 100)), attempt("b", counts=(2, 2))]
    config = attempt(start=150)["config"]
    with pytest.raises(ValueError, match="prior bound"):
        validate_resume_start(previous, config, abrupt_suffix_resolved=True)


def test_same_start_and_boundary_rejected():
    for start in (100, 110, 120):
        with pytest.raises(ValueError, match="prior bound"):
            validate_resume_start([attempt()], attempt(start=start)["config"],
                                  abrupt_suffix_resolved=True)


def test_gap_is_statistical_not_bitwise_resume():
    result = validate_resume_start([attempt()], attempt(start=121)["config"],
                                   abrupt_suffix_resolved=True)
    assert result["passed"]
    assert not result["bitwise_uninterrupted_equivalence"]


def test_unknown_crash_suffix_fails_closed():
    with pytest.raises(ValueError, match="unknown crash"):
        validate_resume_start([attempt()], attempt(start=10000)["config"])


@pytest.mark.parametrize("key,value", [("rollout_mode", "multi"),
    ("mirror_self_play_deals", True), ("paired_seat_average_returns", True),
    ("fixed_training_deal_stream", False), ("worker_seed_base", None)])
def test_unsupported_counter_interpretations_rejected(key, value):
    row = attempt()
    row["config"][key] = value
    with pytest.raises(ValueError):
        single_env_intervals(row["config"], row["accounting"])


def test_duplicate_workers_and_inconsistent_sums_rejected():
    row = attempt()
    for change in ("duplicate", "sum"):
        bad = copy.deepcopy(row["accounting"])
        if change == "duplicate":
            bad["session_worker_counts"][1]["worker_id"] = 0
        else:
            bad["session_completed_hands"] += 1
        with pytest.raises(ValueError):
            single_env_intervals(row["config"], bad)


def test_interval_accounting_matches_explicit_identity_sets():
    rng = random.Random(20260904)
    for _ in range(200):
        attempts = [attempt(str(i), start=rng.randrange(25),
                            counts=(rng.randrange(15), rng.randrange(15)),
                            seed=rng.choice((700, 900))) for i in range(8)]
        identities = []
        for row in attempts:
            for interval in single_env_intervals(row["config"], row["accounting"]):
                identities.extend((interval["worker_seed"], interval["env_index"], index)
                                  for index in range(interval["start"], interval["end"]))
        result = summarize_overlap(attempts)
        assert result["executed_hands"] == len(identities)
        assert result["unique_evidenced_deal_identities"] == len(set(identities))
