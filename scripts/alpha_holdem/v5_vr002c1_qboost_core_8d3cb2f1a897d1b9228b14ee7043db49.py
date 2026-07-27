"""VR002C1 training-only centralized Q-boost primitives.

This module is deliberately independent of the deployable AlphaHoldem actor.  It
contains no environment loop, checkpoint selection, networking, or evaluator code.
The immutable design authority is:

  reports/v5_vr002c1_cpu_default_generator_correction_preregistration_
  8d3cb2f1a897d1b9228b14ee7043db49_20260723.json

CENTRAL895 is a serialization/audit contract: 886 learned float32 features followed
by a nine-action legal-mask sidecar.  Rollouts store ``CompactCentralState`` objects,
not a dense T-by-2-by-895 tensor.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import torch
from torch import nn
import torch.nn.functional as F


DESIGN_ID = "VR002C1_CPU_DEFAULT_GENERATOR_CORRECTED_FROZEN_H11_FAITHFUL_QBOOST_CORE"
IDENTITY_TOKEN = "8d3cb2f1a897d1b9228b14ee7043db49"

NUM_ACTIONS = 9
CARD6_SHAPE = (6, 4, 13)
CARD7_SHAPE = (7, 4, 13)
ACTION25_SHAPE = (25, 4, 5)
PUBLIC_SIZE = 22
LEARNED_FEATURE_FLOATS = 886
CENTRAL_SERIALIZED_FLOATS = 895
Q_INIT_SEED = 2026072302
Q_MINIBATCH_SEED = 2026072303
Q_LEARNING_RATE = 0.0003
GAMMA = 0.999
LAMBDA = 0.95
NORMALIZATION_EPSILON = 1e-8
POOL_MEMBER_IDS = (109, 115, 120, 129, 103)

_CARD6_FLOATS = int(np.prod(CARD6_SHAPE))
_CARD7_FLOATS = int(np.prod(CARD7_SHAPE))
_ACTION_FLOATS = int(np.prod(ACTION25_SHAPE))
assert _CARD7_FLOATS + _ACTION_FLOATS + PUBLIC_SIZE == LEARNED_FEATURE_FLOATS
assert LEARNED_FEATURE_FLOATS + NUM_ACTIONS == CENTRAL_SERIALIZED_FLOATS


def _float32_array(
    value: Any,
    shape: tuple[int, ...],
    name: str,
    *,
    finite: bool = True,
) -> np.ndarray:
    array = np.asarray(value, dtype=np.float32)
    if array.shape != shape:
        raise ValueError(f"{name} must have shape {shape}, got {array.shape}")
    if finite and not np.isfinite(array).all():
        raise ValueError(f"{name} contains a non-finite value")
    return np.ascontiguousarray(array)


def _binary_array(value: Any, shape: tuple[int, ...], name: str) -> np.ndarray:
    array = _float32_array(value, shape, name)
    if not np.logical_or(array == 0.0, array == 1.0).all():
        raise ValueError(f"{name} must be exactly binary")
    return array


def _pack_binary(value: np.ndarray) -> bytes:
    return np.packbits(value.reshape(-1).astype(np.uint8), bitorder="little").tobytes()


def _unpack_binary(payload: bytes, count: int, shape: tuple[int, ...]) -> np.ndarray:
    raw = np.frombuffer(payload, dtype=np.uint8)
    values = np.unpackbits(raw, bitorder="little", count=count)
    return values.astype(np.float32, copy=False).reshape(shape)


def _seat(value: int, name: str) -> int:
    result = int(value)
    if result not in (0, 1):
        raise ValueError(f"{name} must be absolute seat 0 or 1")
    return result


def assignment_one_hot(assignment_local: int) -> np.ndarray:
    """Return [self, pool-local-0, ..., pool-local-4]."""
    assignment_local = int(assignment_local)
    if assignment_local < -1 or assignment_local >= len(POOL_MEMBER_IDS):
        raise ValueError("assignment_local must be -1 (self) or a pool-local index 0..4")
    result = np.zeros(6, dtype=np.float32)
    result[assignment_local + 1] = 1.0
    return result


def pool_member_to_local(member_id: int) -> int:
    try:
        return POOL_MEMBER_IDS.index(int(member_id))
    except ValueError as exc:
        raise ValueError(f"member_id is not in frozen pool order: {member_id}") from exc


@dataclass(frozen=True)
class PublicState:
    """The exact pre-step public/assignment fields used by CENTRAL895."""

    active_stack: float
    other_stack: float
    pot: float
    active_street_commit: float
    other_street_commit: float
    to_call: float
    last_bet_size: float
    raise_count: int
    num_actions_this_street: int
    street: int
    active_absolute_seat: int
    hero_absolute_seat: int
    assignment_local: int

    def __post_init__(self) -> None:
        _seat(self.active_absolute_seat, "active_absolute_seat")
        _seat(self.hero_absolute_seat, "hero_absolute_seat")
        if int(self.street) not in (0, 1, 2, 3):
            raise ValueError("street must be 0..3")
        assignment_one_hot(self.assignment_local)
        numeric = (
            self.active_stack,
            self.other_stack,
            self.pot,
            self.active_street_commit,
            self.other_street_commit,
            self.to_call,
            self.last_bet_size,
            self.raise_count,
            self.num_actions_this_street,
        )
        if not all(math.isfinite(float(x)) for x in numeric):
            raise ValueError("public state contains a non-finite value")
        if min(float(x) for x in numeric) < 0.0:
            raise ValueError("public poker quantities must be nonnegative")

    @classmethod
    def from_engine_state(
        cls,
        state: Any,
        *,
        hero_absolute_seat: int,
        assignment_local: int,
    ) -> "PublicState":
        """Capture fields from a pre-step HUNLGameState without retaining the deck."""
        active = _seat(int(state.current_player), "state.current_player")
        other = 1 - active
        active_commit = float(state.street_committed[active])
        other_commit = float(state.street_committed[other])
        return cls(
            active_stack=float(state.stacks[active]),
            other_stack=float(state.stacks[other]),
            pot=float(state.pot),
            active_street_commit=active_commit,
            other_street_commit=other_commit,
            to_call=max(other_commit - active_commit, 0.0),
            last_bet_size=float(state.last_bet_size),
            raise_count=int(state.raise_count),
            num_actions_this_street=int(state.num_actions_this_street),
            street=int(state.street),
            active_absolute_seat=active,
            hero_absolute_seat=_seat(hero_absolute_seat, "hero_absolute_seat"),
            assignment_local=int(assignment_local),
        )

    def encode(self, focal_absolute_seat: int) -> np.ndarray:
        focal = _seat(focal_absolute_seat, "focal_absolute_seat")
        street = np.zeros(4, dtype=np.float32)
        street[int(self.street)] = 1.0
        result = np.asarray(
            [
                float(self.active_stack) / 200.0,
                float(self.other_stack) / 200.0,
                float(self.pot) / 400.0,
                float(self.active_street_commit) / 200.0,
                float(self.other_street_commit) / 200.0,
                float(self.to_call) / 200.0,
                float(self.last_bet_size) / 200.0,
                float(self.raise_count) / 200.0,
                float(self.num_actions_this_street) / 200.0,
                *street.tolist(),
                float(int(self.active_absolute_seat) == 1),
                float(focal == 1),
                float(int(self.hero_absolute_seat) == 1),
                *assignment_one_hot(self.assignment_local).tolist(),
            ],
            dtype=np.float32,
        )
        if result.shape != (PUBLIC_SIZE,):
            raise AssertionError(f"internal public layout error: {result.shape}")
        return result


@dataclass(frozen=True)
class CompactCentralState:
    """Lossless compact CPU representation of one physical pre-step state."""

    card6_bits: bytes
    action25_f32: bytes
    other_hole_cards: tuple[int, int]
    legal_bits: bytes
    public: PublicState

    @classmethod
    def from_arrays(
        cls,
        actor_card6: Any,
        actor_action25: Any,
        other_hole_cards: Sequence[int],
        legal_mask: Any,
        public: PublicState,
    ) -> "CompactCentralState":
        cards = _binary_array(actor_card6, CARD6_SHAPE, "actor_card6")
        actions = _float32_array(actor_action25, ACTION25_SHAPE, "actor_action25")
        legal = _binary_array(legal_mask, (NUM_ACTIONS,), "legal_mask")
        if float(legal.sum()) < 1.0:
            raise ValueError("legal_mask must contain at least one legal action")
        holes = tuple(int(x) for x in other_hole_cards)
        if len(holes) != 2 or holes[0] == holes[1] or any(x < 0 or x >= 52 for x in holes):
            raise ValueError("other_hole_cards must contain two distinct card ids 0..51")
        if not isinstance(public, PublicState):
            raise TypeError("public must be PublicState")
        return cls(
            card6_bits=_pack_binary(cards),
            action25_f32=actions.tobytes(order="C"),
            other_hole_cards=(holes[0], holes[1]),
            legal_bits=_pack_binary(legal),
            public=public,
        )

    def decode_actor_cards(self) -> np.ndarray:
        return _unpack_binary(self.card6_bits, _CARD6_FLOATS, CARD6_SHAPE)

    def decode_actions(self) -> np.ndarray:
        values = np.frombuffer(self.action25_f32, dtype=np.float32)
        if values.size != _ACTION_FLOATS:
            raise ValueError("corrupt compact action payload")
        return values.copy().reshape(ACTION25_SHAPE)

    def decode_legal(self) -> np.ndarray:
        return _unpack_binary(self.legal_bits, NUM_ACTIONS, (NUM_ACTIONS,))

    def decode_cards7(self) -> np.ndarray:
        cards = np.zeros(CARD7_SHAPE, dtype=np.float32)
        cards[:6] = self.decode_actor_cards()
        for card in self.other_hole_cards:
            cards[6, card % 4, card // 4] = 1.0
        return cards

    def decode_focal_views(
        self,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return cards7, actions25, public[2,22], and legal9."""
        public_two = np.stack((self.public.encode(0), self.public.encode(1)), axis=0)
        return self.decode_cards7(), self.decode_actions(), public_two, self.decode_legal()

    def serialize_focal(self, focal_absolute_seat: int) -> np.ndarray:
        return encode_central895(
            self.decode_actor_cards(),
            self.decode_actions(),
            self.other_hole_cards,
            self.public,
            self.decode_legal(),
            focal_absolute_seat=focal_absolute_seat,
        )


def encode_central895(
    actor_card6: Any,
    actor_action25: Any,
    other_hole_cards: Sequence[int],
    public: PublicState,
    legal_mask: Any,
    *,
    focal_absolute_seat: int,
) -> np.ndarray:
    """Materialize one audit-format CENTRAL895 row (not rollout storage)."""
    compact = CompactCentralState.from_arrays(
        actor_card6, actor_action25, other_hole_cards, legal_mask, public
    )
    cards7 = compact.decode_cards7()
    learned = np.concatenate(
        (
            cards7.reshape(-1),
            compact.decode_actions().reshape(-1),
            public.encode(focal_absolute_seat),
        )
    ).astype(np.float32, copy=False)
    result = np.concatenate((learned, compact.decode_legal())).astype(np.float32, copy=False)
    if result.shape != (CENTRAL_SERIALIZED_FLOATS,):
        raise AssertionError(f"internal CENTRAL895 layout error: {result.shape}")
    return result


def encode_central_view(
    actor_card6: Any,
    actor_action25: Any,
    other_hole_cards: Sequence[int],
    public: PublicState,
    legal_mask: Any,
    *,
    focal_absolute_seat: int,
) -> np.ndarray:
    """Stable public alias for the registered CENTRAL895 audit encoding."""
    return encode_central895(
        actor_card6,
        actor_action25,
        other_hole_cards,
        public,
        legal_mask,
        focal_absolute_seat=focal_absolute_seat,
    )


build_central_view = encode_central_view


def split_central895(serialized: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Split one or more CENTRAL895 audit rows; preserves leading dimensions."""
    value = np.asarray(serialized, dtype=np.float32)
    if value.shape[-1:] != (CENTRAL_SERIALIZED_FLOATS,):
        raise ValueError("serialized CENTRAL895 has wrong trailing dimension")
    cards_end = _CARD7_FLOATS
    actions_end = cards_end + _ACTION_FLOATS
    public_end = actions_end + PUBLIC_SIZE
    lead = value.shape[:-1]
    cards = value[..., :cards_end].reshape(*lead, *CARD7_SHAPE)
    actions = value[..., cards_end:actions_end].reshape(*lead, *ACTION25_SHAPE)
    public = value[..., actions_end:public_end]
    legal = value[..., public_end:]
    return cards, actions, public, legal


def decode_compact_batch(
    states: Sequence[CompactCentralState],
    *,
    device: torch.device | str | None = None,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """Decode only a physical-row minibatch, with focal public shape [B,2,22]."""
    if not states:
        raise ValueError("cannot decode an empty compact batch")
    decoded = [state.decode_focal_views() for state in states]
    cards = torch.from_numpy(np.stack([row[0] for row in decoded]))
    actions = torch.from_numpy(np.stack([row[1] for row in decoded]))
    public_two = torch.from_numpy(np.stack([row[2] for row in decoded]))
    legal = torch.from_numpy(np.stack([row[3] for row in decoded]))
    if device is not None:
        cards = cards.to(device)
        actions = actions.to(device)
        public_two = public_two.to(device)
        legal = legal.to(device)
    return cards, actions, public_two, legal


@dataclass(frozen=True)
class CompactTraceRow:
    """One complete post-step chronological row.

    The mapped action is represented by immutable type/amount primitives rather than
    retaining a mutable engine object.
    """

    uid: str
    step_index: int
    state: CompactCentralState
    request_model_id: int
    actor_generation: int
    selected_slot: int
    mapped_action_type: int
    mapped_action_amount: float
    old_log_probability: float
    legacy_scalar_value: float
    pi_ref9: tuple[float, ...]
    done: bool
    training_reward: tuple[float, float]
    realized_payoff: tuple[float, float]

    def __post_init__(self) -> None:
        if not self.uid or int(self.step_index) < 0:
            raise ValueError("trace UID must be nonempty and step_index nonnegative")
        if not isinstance(self.state, CompactCentralState):
            raise TypeError("state must be CompactCentralState")
        slot = int(self.selected_slot)
        if slot < 0 or slot >= NUM_ACTIONS:
            raise ValueError("selected_slot must be 0..8")
        pi = validate_serving_policy(
            self.pi_ref9,
            self.state.decode_legal(),
            selected_slot=slot,
            old_log_probability=self.old_log_probability,
        )
        object.__setattr__(self, "pi_ref9", tuple(float(x) for x in pi))
        if not math.isfinite(float(self.legacy_scalar_value)):
            raise ValueError("legacy_scalar_value must be finite")
        if not math.isfinite(float(self.mapped_action_amount)):
            raise ValueError("mapped_action_amount must be finite")
        if float(self.mapped_action_amount) < 0.0:
            raise ValueError("mapped_action_amount must be nonnegative")
        request_model_id = int(self.request_model_id)
        if request_model_id != -1 and request_model_id not in POOL_MEMBER_IDS:
            raise ValueError("request_model_id is not hero or a frozen pool member")
        generation = int(self.actor_generation)
        if request_model_id == -1:
            if (
                generation < 0
                or generation > 2**24
                or int(np.float32(generation)) != generation
            ):
                raise ValueError(
                    "hero actor_generation must be nonnegative and exactly float32"
                )
        elif generation != -1:
            raise ValueError("frozen pool rows require actor_generation=-1")
        for pair_name, pair in (
            ("training_reward", self.training_reward),
            ("realized_payoff", self.realized_payoff),
        ):
            if len(pair) != 2 or not all(math.isfinite(float(x)) for x in pair):
                raise ValueError(f"{pair_name} must be a finite two-vector")


def validate_serving_policy(
    pi_ref9: Any,
    legal_mask: Any,
    *,
    selected_slot: int | None = None,
    old_log_probability: float | None = None,
    atol: float = 2e-6,
) -> np.ndarray:
    pi = _float32_array(pi_ref9, (NUM_ACTIONS,), "pi_ref9")
    legal = _binary_array(legal_mask, (NUM_ACTIONS,), "legal_mask")
    if (pi < 0.0).any():
        raise ValueError("pi_ref9 contains negative probability")
    if not np.all(pi[legal == 0.0] == 0.0):
        raise ValueError("pi_ref9 has nonzero illegal mass")
    if not math.isclose(float(pi.sum()), 1.0, rel_tol=0.0, abs_tol=atol):
        raise ValueError("pi_ref9 legal mass must sum to one")
    if selected_slot is not None:
        selected_slot = int(selected_slot)
        if selected_slot < 0 or selected_slot >= NUM_ACTIONS or legal[selected_slot] != 1.0:
            raise ValueError("selected slot is illegal")
        if pi[selected_slot] <= 0.0:
            raise ValueError("selected slot has zero serving probability")
        if old_log_probability is not None:
            expected = math.log(float(pi[selected_slot]))
            if not math.isclose(
                expected, float(old_log_probability), rel_tol=0.0, abs_tol=atol
            ):
                raise ValueError("old log probability does not match pi_ref9")
    return pi


def validate_complete_hand_trace(
    rows: Sequence[CompactTraceRow],
    *,
    reference_generation: int,
) -> dict[str, Any]:
    if not rows:
        raise ValueError("complete hand trace cannot be empty")
    uids = [row.uid for row in rows]
    if len(uids) != len(set(uids)):
        raise ValueError("duplicate trace UID")
    if [row.step_index for row in rows] != list(range(len(rows))):
        raise ValueError("trace step indices are not contiguous zero through T-1")
    done_indices = [i for i, row in enumerate(rows) if row.done]
    if done_indices != [len(rows) - 1]:
        raise ValueError("trace must have exactly one terminal row at T-1")
    for row in rows[:-1]:
        if row.training_reward != (0.0, 0.0):
            raise ValueError("intermediate training reward must be exact zero")
    final_reward = tuple(float(x) for x in rows[-1].training_reward)
    if not math.isclose(final_reward[0] + final_reward[1], 0.0, abs_tol=1e-9):
        raise ValueError("terminal training reward is not exactly zero-sum")
    hero_rows = [row for row in rows if int(row.request_model_id) == -1]
    generations = [int(row.actor_generation) for row in hero_rows]
    pure = bool(hero_rows) and all(g == int(reference_generation) for g in generations)
    actor_indices = [i for i, row in enumerate(rows) if int(row.request_model_id) == -1]
    return {
        "generation_pure": pure,
        "trainable_actor_indices": actor_indices if pure else [],
        "mixed_generation_uids": [] if pure else [row.uid for row in rows],
        "physical_rows": len(rows),
        "focal_rows": 2 * len(rows),
        "terminal_training_reward": final_reward,
    }


class _ResBlock(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, stride: int = 1):
        super().__init__()
        self.conv1 = nn.Conv2d(
            in_channels, out_channels, 3, stride=stride, padding=1, bias=False
        )
        self.bn1 = nn.BatchNorm2d(out_channels)
        self.conv2 = nn.Conv2d(out_channels, out_channels, 3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(out_channels)
        self.shortcut = (
            nn.Identity()
            if stride == 1 and in_channels == out_channels
            else nn.Sequential(
                nn.Conv2d(in_channels, out_channels, 1, stride=stride, bias=False),
                nn.BatchNorm2d(out_channels),
            )
        )

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        out = F.relu(self.bn1(self.conv1(value)))
        out = self.bn2(self.conv2(out))
        return F.relu(out + self.shortcut(value))


class CNNBranch(nn.Module):
    """Independent BatchNorm CNNBranch with the frozen CardPilot topology."""

    def __init__(self, in_channels: int):
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels, 48, 3, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(48)
        self.res1a = _ResBlock(48, 96, stride=2)
        self.res1b = _ResBlock(96, 96)
        self.res2a = _ResBlock(96, 192, stride=2)
        self.res2b = _ResBlock(192, 192)

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        out = F.relu(self.bn1(self.conv1(value)))
        out = self.res1b(self.res1a(out))
        out = self.res2b(self.res2a(out))
        return out.flatten(start_dim=1)


class CentralizedQCritic(nn.Module):
    """Independent CENTRAL895 Q9 critic; legal mask is never a learned input."""

    CARD_EMBED = 192 * 1 * 4
    ACTION_EMBED = 192 * 1 * 2

    def __init__(self) -> None:
        super().__init__()
        self.card_cnn = CNNBranch(7)
        self.action_cnn = CNNBranch(25)
        self.public_fc = nn.Sequential(nn.Linear(PUBLIC_SIZE, 32), nn.ReLU())
        fusion = self.CARD_EMBED + self.ACTION_EMBED + 32
        self.trunk = nn.Sequential(
            nn.Linear(fusion, 2048),
            nn.ReLU(),
            nn.Linear(2048, 1024),
            nn.ReLU(),
            nn.Linear(1024, 512),
            nn.ReLU(),
            nn.Linear(512, 256),
            nn.ReLU(),
        )
        self.q_head = nn.Linear(256, NUM_ACTIONS)
        nn.init.zeros_(self.q_head.weight)
        nn.init.zeros_(self.q_head.bias)

    def _shared(
        self, cards7: torch.Tensor, actions25: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        if cards7.ndim != 4 or tuple(cards7.shape[1:]) != CARD7_SHAPE:
            raise ValueError(f"cards7 must be [B,{CARD7_SHAPE}]")
        if actions25.ndim != 4 or tuple(actions25.shape[1:]) != ACTION25_SHAPE:
            raise ValueError(f"actions25 must be [B,{ACTION25_SHAPE}]")
        if cards7.shape[0] != actions25.shape[0]:
            raise ValueError("cards/actions batch mismatch")
        return self.card_cnn(cards7), self.action_cnn(actions25)

    def _finish(
        self,
        card_embedding: torch.Tensor,
        action_embedding: torch.Tensor,
        public22: torch.Tensor,
    ) -> torch.Tensor:
        if public22.ndim != 2 or public22.shape[1] != PUBLIC_SIZE:
            raise ValueError("public22 must be [B,22]")
        public_embedding = self.public_fc(public22)
        fused = torch.cat((card_embedding, action_embedding, public_embedding), dim=1)
        return self.q_head(self.trunk(fused))

    def forward(
        self,
        cards7: torch.Tensor,
        actions25: torch.Tensor,
        public22: torch.Tensor,
    ) -> torch.Tensor:
        card_embedding, action_embedding = self._shared(cards7, actions25)
        return self._finish(card_embedding, action_embedding, public22)

    def forward_two_focal(
        self,
        cards7: torch.Tensor,
        actions25: torch.Tensor,
        public_two: torch.Tensor,
    ) -> torch.Tensor:
        """Return [physical B, focal 2, action 9], encoding shared tensors once."""
        if public_two.ndim != 3 or tuple(public_two.shape[1:]) != (2, PUBLIC_SIZE):
            raise ValueError("public_two must be [B,2,22]")
        card_embedding, action_embedding = self._shared(cards7, actions25)
        batch = cards7.shape[0]
        if public_two.shape[0] != batch:
            raise ValueError("public_two batch mismatch")
        card_two = (
            card_embedding[:, None, :].expand(-1, 2, -1).reshape(2 * batch, -1)
        )
        action_two = (
            action_embedding[:, None, :].expand(-1, 2, -1).reshape(2 * batch, -1)
        )
        q = self._finish(card_two, action_two, public_two.reshape(2 * batch, PUBLIC_SIZE))
        return q.reshape(batch, 2, NUM_ACTIONS)


def make_q_critic_isolated(seed: int = Q_INIT_SEED) -> CentralizedQCritic:
    """Construct on CPU without advancing global CPU or CUDA RNG states."""
    if int(seed) != Q_INIT_SEED:
        raise ValueError(f"VR002 Q initialization seed must be {Q_INIT_SEED}")
    before = snapshot_torch_rng_states()
    with torch.random.fork_rng(devices=[]):
        torch.random.default_generator.manual_seed(int(seed))
        model = CentralizedQCritic()
    assert_torch_rng_states_equal(before, snapshot_torch_rng_states())
    if torch.count_nonzero(model.q_head.weight).item() != 0:
        raise AssertionError("Q output weight is not exact zero")
    if torch.count_nonzero(model.q_head.bias).item() != 0:
        raise AssertionError("Q output bias is not exact zero")
    return model


initialize_q_critic = make_q_critic_isolated


def initialize_q_optimizer(critic: CentralizedQCritic) -> torch.optim.Adam:
    if not isinstance(critic, CentralizedQCritic):
        raise TypeError("VR002 Q optimizer requires CentralizedQCritic")
    return torch.optim.Adam(
        critic.parameters(),
        lr=Q_LEARNING_RATE,
        betas=(0.9, 0.999),
        eps=1e-8,
        weight_decay=0.0,
    )


def snapshot_torch_rng_states() -> dict[str, Any]:
    """Read-only RNG snapshot; CUDA states are included only if already initialized."""
    return {
        "cpu": torch.get_rng_state().clone(),
        "cuda_initialized": bool(torch.cuda.is_initialized()),
        "cuda": (
            [state.clone() for state in torch.cuda.get_rng_state_all()]
            if torch.cuda.is_initialized()
            else []
        ),
    }


def assert_torch_rng_states_equal(before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    if bool(before["cuda_initialized"]) != bool(after["cuda_initialized"]):
        raise RuntimeError("Q initialization changed CUDA initialization state")
    if not torch.equal(before["cpu"], after["cpu"]):
        raise RuntimeError("Q operation changed global CPU RNG state")
    before_cuda = before["cuda"]
    after_cuda = after["cuda"]
    if len(before_cuda) != len(after_cuda) or any(
        not torch.equal(left, right) for left, right in zip(before_cuda, after_cuda)
    ):
        raise RuntimeError("Q operation changed global CUDA RNG state")


def make_q_minibatch_generator(
    state: torch.Tensor | None = None,
    *,
    seed: int = Q_MINIBATCH_SEED,
) -> torch.Generator:
    generator = torch.Generator(device="cpu")
    if state is None:
        if int(seed) != Q_MINIBATCH_SEED:
            raise ValueError(f"VR002 Q minibatch seed must be {Q_MINIBATCH_SEED}")
        generator.manual_seed(int(seed))
    else:
        generator.set_state(state.detach().cpu().clone())
    return generator


def assert_models_storage_disjoint(actor: nn.Module, critic: nn.Module) -> None:
    """Raise if actor and Q share any Parameter/buffer object or tensor storage."""
    actor_tensors = list(actor.parameters()) + list(actor.buffers())
    critic_tensors = list(critic.parameters()) + list(critic.buffers())
    actor_ids = {id(value) for value in actor_tensors}
    actor_storage = {
        (value.device.type, value.device.index, int(value.untyped_storage().data_ptr()))
        for value in actor_tensors
        if value.numel()
    }
    for value in critic_tensors:
        if id(value) in actor_ids:
            raise RuntimeError("actor/Q share a tensor object")
        if value.numel():
            key = (
                value.device.type,
                value.device.index,
                int(value.untyped_storage().data_ptr()),
            )
            if key in actor_storage:
                raise RuntimeError("actor/Q share tensor storage")


def _validate_qboost_inputs(
    q_values: torch.Tensor,
    policies: torch.Tensor,
    actions: torch.Tensor,
    rewards: torch.Tensor,
    dones: torch.Tensor,
    legal_masks: torch.Tensor | None,
) -> None:
    if q_values.ndim != 3 or tuple(q_values.shape[1:]) != (2, NUM_ACTIONS):
        raise ValueError("q_values must be [T,2,9]")
    length = q_values.shape[0]
    if tuple(policies.shape) != (length, NUM_ACTIONS):
        raise ValueError("policies must be [T,9]")
    if tuple(actions.shape) != (length,):
        raise ValueError("actions must be [T]")
    if tuple(rewards.shape) != (length, 2):
        raise ValueError("rewards must be [T,2]")
    if tuple(dones.shape) != (length,):
        raise ValueError("dones must be [T]")
    tensors = (q_values, policies, rewards, dones)
    if not all(torch.isfinite(value).all().item() for value in tensors):
        raise ValueError("Q-boost input contains non-finite values")
    if length == 0:
        raise ValueError("Q-boost hand cannot be empty")
    if not torch.all((actions >= 0) & (actions < NUM_ACTIONS)).item():
        raise ValueError("actions contain an out-of-range slot")
    if not torch.allclose(
        policies.sum(dim=1),
        torch.ones(length, device=policies.device, dtype=policies.dtype),
        rtol=0.0,
        atol=2e-6,
    ):
        raise ValueError("policy rows must sum to one")
    if (policies < 0).any().item():
        raise ValueError("policy contains negative probability")
    if legal_masks is not None:
        if tuple(legal_masks.shape) != (length, NUM_ACTIONS):
            raise ValueError("legal_masks must be [T,9]")
        if not torch.all((legal_masks == 0) | (legal_masks == 1)).item():
            raise ValueError("legal_masks must be exactly binary")
        if not torch.all(policies[legal_masks == 0] == 0).item():
            raise ValueError("policy contains nonzero illegal mass")
        if not torch.all(
            legal_masks.gather(1, actions.to(dtype=torch.long)[:, None]).squeeze(1) == 1
        ).item():
            raise ValueError("selected action is illegal")
    expected_done = torch.zeros_like(dones)
    expected_done[-1] = 1
    if not torch.equal(dones.to(dtype=torch.bool), expected_done.to(dtype=torch.bool)):
        raise ValueError("one hand must have done=false except at T-1")


def expected_sarsa_qboost(
    q_values: torch.Tensor,
    policies: torch.Tensor,
    actions: torch.Tensor,
    rewards: torch.Tensor,
    dones: torch.Tensor,
    *,
    gamma: float = GAMMA,
    lam: float = LAMBDA,
    legal_masks: torch.Tensor | None = None,
) -> dict[str, torch.Tensor]:
    """Exact two-focal Expected-SARSA(lambda) and stop-gradient Q-boost tensors.

    ``q_values`` must already come from the frozen Qbar snapshot. ``policies[t]`` is
    the exact active policy at state t (current hero/self or captured pool pi_ref).
    """
    if float(gamma) != GAMMA or float(lam) != LAMBDA:
        raise ValueError("VR002 requires gamma=.999 and lambda=.95")
    _validate_qboost_inputs(q_values, policies, actions, rewards, dones, legal_masks)
    q_bar = q_values.detach()
    policy = policies.detach().to(dtype=q_bar.dtype)
    reward = rewards.detach().to(dtype=q_bar.dtype)
    done = dones.to(dtype=q_values.dtype)
    values = (q_bar * policy[:, None, :]).sum(dim=-1)
    gather_index = actions.to(dtype=torch.long)[:, None, None].expand(-1, 2, 1)
    q_taken = q_bar.gather(dim=2, index=gather_index).squeeze(-1)
    trace = torch.empty_like(q_taken)
    delta = torch.empty_like(q_taken)
    accumulator = torch.zeros(2, dtype=q_values.dtype, device=q_values.device)
    for index in range(q_values.shape[0] - 1, -1, -1):
        next_value = (
            torch.zeros_like(accumulator)
            if index == q_values.shape[0] - 1
            else values[index + 1]
        )
        continuation = 1.0 - done[index]
        delta[index] = (
            reward[index] + float(gamma) * continuation * next_value - q_taken[index]
        )
        accumulator = (
            delta[index]
            + float(gamma) * float(lam) * continuation * accumulator
        )
        trace[index] = accumulator
    q_target = (q_taken + trace).detach()
    advantage = (q_taken - values + trace).detach()
    return {
        "v": values.detach(),
        "q_taken": q_taken.detach(),
        "delta": delta.detach(),
        "trace": trace.detach(),
        "q_target": q_target,
        "advantage": advantage,
    }


def select_active_focal(
    two_focal_values: torch.Tensor, active_absolute_seats: torch.Tensor
) -> torch.Tensor:
    """Select focal i=active absolute seat without sign transformations."""
    if two_focal_values.ndim != 2 or two_focal_values.shape[1] != 2:
        raise ValueError("two_focal_values must be [T,2]")
    seats = active_absolute_seats.to(
        device=two_focal_values.device, dtype=torch.long
    )
    if tuple(seats.shape) != (two_focal_values.shape[0],):
        raise ValueError("active_absolute_seats must be [T]")
    if not torch.all((seats == 0) | (seats == 1)).item():
        raise ValueError("active_absolute_seats must be 0 or 1")
    return two_focal_values.gather(1, seats[:, None]).squeeze(1)


def q_regression_loss(
    q_predictions: torch.Tensor,
    actions: torch.Tensor,
    fixed_q_targets: torch.Tensor,
) -> torch.Tensor:
    """Registered critic objective: mean 0.5*(Q_i(s,a)-fixed_target_i)^2."""
    if q_predictions.ndim != 3 or tuple(q_predictions.shape[1:]) != (2, NUM_ACTIONS):
        raise ValueError("q_predictions must be [B,2,9]")
    batch = q_predictions.shape[0]
    if tuple(actions.shape) != (batch,) or tuple(fixed_q_targets.shape) != (batch, 2):
        raise ValueError("actions must be [B] and fixed_q_targets [B,2]")
    if not torch.isfinite(q_predictions).all().item() or not torch.isfinite(
        fixed_q_targets
    ).all().item():
        raise ValueError("Q regression tensors must be finite")
    index = actions.to(device=q_predictions.device, dtype=torch.long)
    if not torch.all((index >= 0) & (index < NUM_ACTIONS)).item():
        raise ValueError("Q regression action is out of range")
    selected = q_predictions.gather(
        2, index[:, None, None].expand(-1, 2, 1)
    ).squeeze(-1)
    return 0.5 * (selected - fixed_q_targets.detach()).square().mean()


def paired_legacy_gae(
    legacy_values: Any,
    active_absolute_seats: Any,
    terminal_training_reward: Sequence[float],
    *,
    actor_row_mask: Any | None = None,
    gamma: float = GAMMA,
    lam: float = LAMBDA,
) -> np.ndarray:
    """Reproduce inherited per-player own-decision GAE on chronological row UIDs.

    Non-actor rows remain NaN.  Each absolute player's terminal reward is assigned to
    that player's last admitted own-decision row, exactly as the parent finalizer did.
    """
    if float(gamma) != GAMMA or float(lam) != LAMBDA:
        raise ValueError("VR002 requires gamma=.999 and lambda=.95")
    values = np.asarray(legacy_values, dtype=np.float64)
    seats = np.asarray(active_absolute_seats, dtype=np.int64)
    if values.ndim != 1 or seats.shape != values.shape or values.size == 0:
        raise ValueError("legacy_values and active seats must be same nonempty vector")
    if not np.isfinite(values).all() or not np.isin(seats, (0, 1)).all():
        raise ValueError("invalid legacy values or active seats")
    terminal = np.asarray(terminal_training_reward, dtype=np.float64)
    if terminal.shape != (2,) or not np.isfinite(terminal).all():
        raise ValueError("terminal_training_reward must be a finite two-vector")
    if not math.isclose(float(terminal.sum()), 0.0, abs_tol=1e-9):
        raise ValueError("terminal_training_reward must be zero-sum")
    mask = (
        np.ones(values.shape, dtype=bool)
        if actor_row_mask is None
        else np.asarray(actor_row_mask, dtype=bool)
    )
    if mask.shape != values.shape:
        raise ValueError("actor_row_mask shape mismatch")
    result = np.full(values.shape, np.nan, dtype=np.float64)
    for player in (0, 1):
        indices = np.flatnonzero(mask & (seats == player))
        if indices.size == 0:
            continue
        own_values = values[indices]
        own_rewards = np.zeros(indices.size, dtype=np.float64)
        own_rewards[-1] = terminal[player]
        own_dones = np.zeros(indices.size, dtype=np.float64)
        own_dones[-1] = 1.0
        accumulator = 0.0
        for local in range(indices.size - 1, -1, -1):
            next_value = 0.0 if local == indices.size - 1 else own_values[local + 1]
            continuation = 1.0 - own_dones[local]
            delta = (
                own_rewards[local]
                + float(gamma) * continuation * next_value
                - own_values[local]
            )
            accumulator = (
                delta
                + float(gamma) * float(lam) * continuation * accumulator
            )
            result[indices[local]] = accumulator
    return result


def population_variance(values: Any) -> float:
    array = np.asarray(values, dtype=np.float64)
    if array.ndim != 1 or array.size == 0 or not np.isfinite(array).all():
        raise ValueError("population variance requires a finite nonempty vector")
    return float(np.var(array, ddof=0))


def normalize_population(
    values: torch.Tensor, epsilon: float = NORMALIZATION_EPSILON
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    if float(epsilon) != NORMALIZATION_EPSILON:
        raise ValueError("VR002 normalization epsilon must be exactly 1e-8")
    if values.numel() == 0 or not torch.isfinite(values).all().item():
        raise ValueError("normalization requires finite nonempty values")
    detached = values.detach()
    mean = detached.mean()
    std = detached.std(unbiased=False)
    return (detached - mean) / (std + float(epsilon)), mean, std


def exact_median(values: Iterable[float]) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered or not all(math.isfinite(value) for value in ordered):
        raise ValueError("median requires finite nonempty values")
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def variance_ratio(qboost_advantage: Any, legacy_gae: Any) -> float:
    numerator = population_variance(qboost_advantage)
    denominator = population_variance(legacy_gae)
    if not denominator > 1e-12:
        raise ValueError("legacy GAE population variance must be strictly above 1e-12")
    ratio = numerator / denominator
    if not math.isfinite(ratio):
        raise ValueError("variance ratio is non-finite")
    return ratio


def legal_q_dispersion(q_values: Any, legal_masks: Any) -> np.ndarray:
    q = np.asarray(q_values, dtype=np.float64)
    legal = np.asarray(legal_masks)
    if q.ndim != 2 or q.shape[1] != NUM_ACTIONS or legal.shape != q.shape:
        raise ValueError("q_values/legal_masks must both be [N,9]")
    if not np.isfinite(q).all() or not np.isin(legal, (0, 1)).all():
        raise ValueError("invalid Q values or legal masks")
    result = []
    for row_q, row_legal in zip(q, legal):
        chosen = row_q[row_legal.astype(bool)]
        if chosen.size >= 2:
            result.append(float(np.std(chosen, ddof=0)))
    return np.asarray(result, dtype=np.float64)


def final_half(values: Sequence[float], *, minimum_updates: int = 20) -> list[float]:
    if len(values) < int(minimum_updates):
        raise ValueError(f"requires at least {minimum_updates} valid updates")
    start = len(values) // 2
    return [float(value) for value in values[start:]]


def _self_test() -> dict[str, Any]:
    checks: list[str] = []
    cards = np.zeros(CARD6_SHAPE, dtype=np.float32)
    cards[0, 0, 0] = 1.0
    cards[0, 1, 1] = 1.0
    cards[4, 2, 2] = 1.0
    cards[5] = cards[0] + cards[4]
    actions = np.linspace(0.0, 1.0, _ACTION_FLOATS, dtype=np.float32).reshape(
        ACTION25_SHAPE
    )
    legal = np.asarray([1, 1, 0, 1, 0, 0, 0, 0, 0], dtype=np.float32)
    public = PublicState(
        active_stack=191.5,
        other_stack=187.0,
        pot=21.5,
        active_street_commit=8.5,
        other_street_commit=13.0,
        to_call=4.5,
        last_bet_size=13.0,
        raise_count=2,
        num_actions_this_street=3,
        street=2,
        active_absolute_seat=1,
        hero_absolute_seat=0,
        assignment_local=2,
    )
    compact = CompactCentralState.from_arrays(cards, actions, (50, 51), legal, public)
    cards7, decoded_actions, public_two, decoded_legal = compact.decode_focal_views()
    assert np.array_equal(cards7[:6], cards)
    assert np.array_equal(decoded_actions, actions)
    assert np.array_equal(decoded_legal, legal)
    assert cards7[6].sum() == 2.0
    difference = np.flatnonzero(public_two[0] != public_two[1]).tolist()
    assert difference == [14]
    assert public_two[0, 15] == public_two[1, 15] == 0.0
    assert public_two[0, 19] == public_two[1, 19] == 1.0
    checks.append("compact_codec_and_corrected_central895")

    trace_common = {
        "uid": "run|0|0|deal|0",
        "step_index": 0,
        "state": compact,
        "selected_slot": 0,
        "mapped_action_type": 0,
        "mapped_action_amount": 0.0,
        "old_log_probability": math.log(0.5),
        "legacy_scalar_value": 0.0,
        "pi_ref9": (0.5, 0.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
        "done": True,
        "training_reward": (1.0, -1.0),
        "realized_payoff": (1.0, -1.0),
    }
    CompactTraceRow(
        **trace_common, request_model_id=-1, actor_generation=35051
    )
    CompactTraceRow(
        **trace_common, request_model_id=109, actor_generation=-1
    )
    for bad_request, bad_generation in ((-1, -1), (109, 35051)):
        try:
            CompactTraceRow(
                **trace_common,
                request_model_id=bad_request,
                actor_generation=bad_generation,
            )
        except ValueError:
            pass
        else:
            raise AssertionError("request-model/generation mismatch was accepted")
    checks.append("hero_and_frozen_pool_generation_contract")

    serialized0 = compact.serialize_focal(0)
    serialized1 = compact.serialize_focal(1)
    assert serialized0.shape == serialized1.shape == (CENTRAL_SERIALIZED_FLOATS,)
    assert np.flatnonzero(serialized0 != serialized1).tolist() == [
        _CARD7_FLOATS + _ACTION_FLOATS + 14
    ]
    split = split_central895(np.stack((serialized0, serialized1)))
    assert split[0].shape == (2, *CARD7_SHAPE)
    assert split[1].shape == (2, *ACTION25_SHAPE)
    assert split[2].shape == (2, PUBLIC_SIZE)
    assert split[3].shape == (2, NUM_ACTIONS)
    checks.append("central_serialization_and_focal_isolation")

    cpu_rng = torch.get_rng_state().clone()
    critic = make_q_critic_isolated()
    assert torch.equal(cpu_rng, torch.get_rng_state())
    critic.eval()
    batch = decode_compact_batch([compact, compact])
    with torch.no_grad():
        q_zero = critic.forward_two_focal(batch[0], batch[1], batch[2])
    assert q_zero.shape == (2, 2, NUM_ACTIONS)
    assert torch.count_nonzero(q_zero).item() == 0
    with torch.no_grad():
        critic.q_head.weight.copy_(
            torch.arange(critic.q_head.weight.numel(), dtype=torch.float32).reshape_as(
                critic.q_head.weight
            )
            / float(critic.q_head.weight.numel())
        )
        q_two = critic.forward_two_focal(batch[0], batch[1], batch[2])
        q_sep0 = critic(batch[0], batch[1], batch[2][:, 0])
        q_sep1 = critic(batch[0], batch[1], batch[2][:, 1])
    assert torch.allclose(q_two[:, 0], q_sep0, rtol=1e-6, atol=1e-6)
    assert torch.allclose(q_two[:, 1], q_sep1, rtol=1e-6, atol=1e-6)
    checks.append("isolated_zero_head_q_and_two_focal_forward")

    q = torch.tensor(
        [
            [[1.0, 3.0, 0, 0, 0, 0, 0, 0, 0], [-1.0, -3.0, 0, 0, 0, 0, 0, 0, 0]],
            [[2.0, 4.0, 0, 0, 0, 0, 0, 0, 0], [-2.0, -4.0, 0, 0, 0, 0, 0, 0, 0]],
        ]
    )
    pi = torch.tensor(
        [[0.25, 0.75, 0, 0, 0, 0, 0, 0, 0], [0.5, 0.5, 0, 0, 0, 0, 0, 0, 0]]
    )
    act = torch.tensor([1, 0])
    reward = torch.tensor([[0.0, 0.0], [5.0, -5.0]])
    done = torch.tensor([0.0, 1.0])
    result = expected_sarsa_qboost(q, pi, act, reward, done)
    expected_v = torch.tensor([[2.5, -2.5], [3.0, -3.0]])
    expected_delta1 = torch.tensor([3.0, -3.0])
    expected_delta0 = torch.tensor([0.0 + GAMMA * 3.0 - 3.0, -GAMMA * 3.0 + 3.0])
    expected_trace0 = expected_delta0 + GAMMA * LAMBDA * expected_delta1
    assert torch.allclose(result["v"], expected_v, rtol=0, atol=1e-7)
    assert torch.allclose(result["delta"][1], expected_delta1, rtol=0, atol=1e-7)
    assert torch.allclose(result["trace"][0], expected_trace0, rtol=0, atol=1e-6)
    assert not result["advantage"].requires_grad
    assert not result["q_target"].requires_grad
    checks.append("expected_sarsa_lambda_and_qboost_math")

    active = select_active_focal(result["advantage"], torch.tensor([1, 0]))
    expected_active = torch.stack(
        (result["advantage"][0, 1], result["advantage"][1, 0])
    )
    assert torch.equal(active, expected_active)
    prediction = torch.zeros(2, 2, NUM_ACTIONS, requires_grad=True)
    target = torch.ones(2, 2)
    loss = q_regression_loss(prediction, act, target)
    assert math.isclose(float(loss), 0.5, abs_tol=1e-8)
    loss.backward()
    assert target.grad is None
    checks.append("active_focal_selection_and_half_mse")

    legacy = paired_legacy_gae(
        [1.0, -2.0, 1.5, -1.0],
        [0, 1, 0, 1],
        [4.0, -4.0],
        actor_row_mask=[1, 1, 1, 1],
    )
    expected_p0_last = 4.0 - 1.5
    expected_p0_first = GAMMA * 1.5 - 1.0 + GAMMA * LAMBDA * expected_p0_last
    assert math.isclose(legacy[2], expected_p0_last, abs_tol=1e-12)
    assert math.isclose(legacy[0], expected_p0_first, abs_tol=1e-12)
    checks.append("paired_legacy_own_decision_gae")

    normalized, mean, std = normalize_population(torch.tensor([1.0, 2.0, 3.0]))
    assert math.isclose(float(mean), 2.0)
    assert math.isclose(float(std), math.sqrt(2.0 / 3.0), rel_tol=1e-6)
    assert abs(float(normalized.mean())) < 1e-6
    assert exact_median([4, 1, 3, 2]) == 2.5
    assert population_variance([1, 2, 3]) == 2.0 / 3.0
    assert variance_ratio([0, 2], [0, 1]) == 4.0
    dispersion = legal_q_dispersion(
        [[0, 2, 99, 0, 0, 0, 0, 0, 0]], [[1, 1, 0, 0, 0, 0, 0, 0, 0]]
    )
    assert np.array_equal(dispersion, np.asarray([1.0]))
    assert final_half(list(range(20))) == list(map(float, range(10, 20)))
    checks.append("registered_exact_statistics")

    generator = make_q_minibatch_generator()
    generator_state = generator.get_state().clone()
    first = torch.randperm(32, generator=generator)
    restored = make_q_minibatch_generator(generator_state)
    assert torch.equal(first, torch.randperm(32, generator=restored))
    checks.append("dedicated_persistable_minibatch_rng")

    actor = nn.Linear(3, 2)
    assert_models_storage_disjoint(actor, critic)
    actor.zero_grad(set_to_none=True)
    critic.zero_grad(set_to_none=True)
    critic.train()
    q_loss = critic.forward_two_focal(batch[0], batch[1], batch[2]).square().mean()
    q_loss.backward()
    assert all(parameter.grad is None for parameter in actor.parameters())
    checks.append("actor_q_storage_and_gradient_isolation")

    return {"status": "PASS", "checks": len(checks), "names": checks}


def run_contract_tests() -> dict[str, Any]:
    """Run deterministic CPU-only core contracts and return a JSON-safe result."""
    return _self_test()


if __name__ == "__main__":
    import json

    print(json.dumps(run_contract_tests(), sort_keys=True))
