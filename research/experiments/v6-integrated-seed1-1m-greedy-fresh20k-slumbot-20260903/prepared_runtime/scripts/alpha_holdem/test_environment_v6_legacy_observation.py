from types import SimpleNamespace

import numpy as np
import pytest

from alpha_holdem.environment_v6 import HUNLEnvironmentV6
from alpha_holdem.legacy_observation_bridge_v6 import (
    BRIDGE_CONTRACT,
    legacy_observation_from_state,
)
from alpha_holdem.policy_contract_v6 import (
    CONTRACT_VERSION,
    action_table,
    training_metadata,
    validate_resume,
)


def args(**updates):
    values = dict(
        env_version="v6legacyv4obs",
        starting_stack=200,
        v6_rebind_legacy_weights=True,
        resume="standard10.pt",
        allow_resume=True,
        reset_optimizer=True,
        reset_hand_counter=True,
        hero_preflop_strategy="model",
        pool_strategy="all",
        action_q_counterfactual_dataset="",
        ppo_replay_buffer_iterations=0,
        run_id="new-bridge-run",
    )
    values.update(updates)
    return SimpleNamespace(**values)


def test_training_metadata_explicitly_binds_physical_v6_and_v4_observation():
    metadata = training_metadata(args())
    assert metadata["env_version"] == "v6legacyv4obs"
    assert metadata["rules_version"] == "hunl_integer_chips_v1"
    assert metadata["policy_contract"] == CONTRACT_VERSION
    assert metadata["obs_version"] == metadata["model_obs_version"] == "v4"
    assert metadata["observation_bridge_contract"] == BRIDGE_CONTRACT
    assert metadata["raise_action_mapping"] == "preflop_pot_fraction_v2"
    assert metadata["action_space_version"] == "9slot_preflop_pot_fraction_v2_bridge_v1"


def test_resume_distinguishes_rebind_from_native_bridge_continuation():
    source = {"env_version": "v55preflopv2v4obs"}
    validate_resume(args(), source)
    checkpoint = training_metadata(args())
    continuation = args(v6_rebind_legacy_weights=False, run_id="continued")
    validate_resume(continuation, checkpoint)
    with pytest.raises(ValueError):
        validate_resume(args(), checkpoint)
    with pytest.raises(ValueError):
        validate_resume(args(env_version="v6", v6_rebind_legacy_weights=False), checkpoint)


def test_rebind_allows_fresh_v6_replay_but_rejects_old_replay_import():
    replay_args = args(ppo_replay_buffer_iterations=2)
    metadata = training_metadata(replay_args)
    assert metadata["legacy_weights_rebound_to_new_contract"] is True
    validate_resume(replay_args, {"env_version": "v55preflopv2v4obs"})
    with pytest.raises(ValueError, match="old-contract replay"):
        validate_resume(replay_args, {
            "env_version": "v55preflopv2v4obs",
            "ppo_replay_entries": [{"iteration": 1, "blocks": []}],
            "ppo_replay_cumulative_rows": 1,
        })


def test_legacy_observation_environment_exact_multistreet_parity():
    rng = np.random.default_rng(2026090110)
    observed = [0, 0, 0, 0]
    decisions = 0
    for _ in range(600):
        deck = rng.permutation(52).astype(int).tolist()
        env = HUNLEnvironmentV6(observation_style="legacy_v4")
        obs = env.reset_with_deck(deck)
        while not env.state.is_terminal():
            expected, legacy_table = legacy_observation_from_state(env.state.core)
            mask, physical_table = action_table(env.state.core)
            assert {action for action in legacy_table if action is not None}.issubset(
                {action for action in physical_table if action is not None}
            )
            for key in ("card_info", "action_info", "extra_info", "legal_mask"):
                assert np.array_equal(obs[key], expected[key])
            assert obs["player"] == expected["player"] == env.state.current_player
            assert np.array_equal(
                obs["legal_mask"],
                np.asarray([action is not None for action in legacy_table], dtype=np.float32),
            )
            observed[int(env.state.street)] += 1
            decisions += 1
            legal = np.flatnonzero(obs["legal_mask"])
            # Outcome-blind reach distribution: passive-biased but covers raises.
            slot = 1 if rng.random() < 0.60 else int(legal[rng.integers(len(legal))])
            obs, _, done = env.step(slot)
            if done:
                break
    assert decisions >= 1000
    assert all(count > 50 for count in observed)


def test_default_v6_slot_contract_remains_distinct_at_preflop_root():
    deck = list(range(52))
    legacy = HUNLEnvironmentV6(observation_style="legacy_v4")
    native = HUNLEnvironmentV6(observation_style="v6")
    legacy_obs = legacy.reset_with_deck(deck)
    native_obs = native.reset_with_deck(deck)
    assert not np.array_equal(legacy_obs["legal_mask"], native_obs["legal_mask"])
    assert {
        action.amount for action in legacy.last_action_table if action is not None
    } == {
        action.amount for action in native.last_action_table if action is not None
    }
