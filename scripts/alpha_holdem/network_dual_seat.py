"""Pure-weight dual-seat policy wrapper.

Both frozen actors are part of one ``nn.Module`` and the public seat feature
selects their output inside ``forward``.  There is no evaluator-side action
override or post-network policy rule.
"""

from __future__ import annotations

import torch
import torch.nn as nn


class DualSeatAlphaHoldemNet(nn.Module):
    """Route BB rows to one actor and SB rows to another inside the network."""

    architecture = "dual_seat_v1"
    requires_position_feature = True
    position_adapter_hidden = 0

    def __init__(self, *, sb_model: nn.Module, bb_model: nn.Module) -> None:
        super().__init__()
        self.sb_model = sb_model
        self.bb_model = bb_model
        self.num_actions = int(sb_model.num_actions)
        if int(bb_model.num_actions) != self.num_actions:
            raise ValueError("SB and BB actors must have the same action count")

    def forward(
        self,
        card_info: torch.Tensor,
        action_info: torch.Tensor,
        extra_info: torch.Tensor,
        legal_mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        if extra_info.ndim != 2 or extra_info.shape[1] < 3:
            raise ValueError(
                "dual-seat policy requires extra_info[:, 2] public seat feature"
            )
        base_extra = extra_info[:, :2]
        is_sb = extra_info[:, 2].round().clamp(0, 1).bool()
        # Evaluation uses one decision row per call.  Fast-path a homogeneous
        # batch so the inactive frozen backbone is not evaluated; this is an
        # exact compute optimization and does not alter policy selection.
        if bool(torch.all(is_sb).item()):
            return self.sb_model(
                card_info,
                action_info,
                base_extra,
                legal_mask,
            )
        if bool(torch.all(~is_sb).item()):
            return self.bb_model(
                card_info,
                action_info,
                base_extra,
                legal_mask,
            )
        sb_logits, sb_value = self.sb_model(
            card_info,
            action_info,
            base_extra,
            legal_mask,
        )
        bb_logits, bb_value = self.bb_model(
            card_info,
            action_info,
            base_extra,
            legal_mask,
        )
        logits = torch.where(is_sb.unsqueeze(-1), sb_logits, bb_logits)
        value = torch.where(is_sb.unsqueeze(-1), sb_value, bb_value)
        return logits, value
