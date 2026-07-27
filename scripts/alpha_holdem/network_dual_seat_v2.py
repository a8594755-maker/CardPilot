"""Position-aware pure-weight dual-seat policy wrapper.

Unlike ``dual_seat_v1``, each frozen actor receives the observation width it
expects.  Legacy actors receive the historical two public scalar features,
while position-adapter (or otherwise position-aware) actors receive the public
seat feature as ``extra_info[:, 2]``.
"""

from __future__ import annotations

import torch
import torch.nn as nn


def _requires_position_feature(model: nn.Module) -> bool:
    return bool(getattr(model, "requires_position_feature", False)) or int(
        getattr(model, "position_adapter_hidden", 0)
    ) > 0


class DualSeatAlphaHoldemNetV2(nn.Module):
    """Route rows by public seat while preserving each actor's input contract."""

    architecture = "dual_seat_v2"
    requires_position_feature = True
    position_adapter_hidden = 0

    def __init__(self, *, sb_model: nn.Module, bb_model: nn.Module) -> None:
        super().__init__()
        self.sb_model = sb_model
        self.bb_model = bb_model
        self.num_actions = int(sb_model.num_actions)
        if int(bb_model.num_actions) != self.num_actions:
            raise ValueError("SB and BB actors must have the same action count")

    @staticmethod
    def _actor_extra(model: nn.Module, extra_info: torch.Tensor) -> torch.Tensor:
        if _requires_position_feature(model):
            return extra_info
        return extra_info[:, :2]

    def _forward_actor(
        self,
        model: nn.Module,
        card_info: torch.Tensor,
        action_info: torch.Tensor,
        extra_info: torch.Tensor,
        legal_mask: torch.Tensor | None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        return model(
            card_info,
            action_info,
            self._actor_extra(model, extra_info),
            legal_mask,
        )

    def forward(
        self,
        card_info: torch.Tensor,
        action_info: torch.Tensor,
        extra_info: torch.Tensor,
        legal_mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        if extra_info.ndim != 2 or extra_info.shape[1] < 3:
            raise ValueError(
                "dual-seat v2 policy requires extra_info[:, 2] public seat feature"
            )
        is_sb = extra_info[:, 2].round().clamp(0, 1).bool()

        # The evaluator normally supplies one row.  The homogeneous fast paths
        # avoid evaluating the inactive actor and exactly preserve its source
        # model call.
        if bool(torch.all(is_sb).item()):
            return self._forward_actor(
                self.sb_model,
                card_info,
                action_info,
                extra_info,
                legal_mask,
            )
        if bool(torch.all(~is_sb).item()):
            return self._forward_actor(
                self.bb_model,
                card_info,
                action_info,
                extra_info,
                legal_mask,
            )

        sb_logits, sb_value = self._forward_actor(
            self.sb_model,
            card_info,
            action_info,
            extra_info,
            legal_mask,
        )
        bb_logits, bb_value = self._forward_actor(
            self.bb_model,
            card_info,
            action_info,
            extra_info,
            legal_mask,
        )
        logits = torch.where(is_sb.unsqueeze(-1), sb_logits, bb_logits)
        value = torch.where(is_sb.unsqueeze(-1), sb_value, bb_value)
        return logits, value
