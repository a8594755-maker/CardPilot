"""
AlphaHoldem network — PyTorch reimplementation.

Pseudo-Siamese architecture:
  - Card branch: CNN on (6, 4, 13) card tensor
  - Action branch: CNN on (25, 4, 5) action history tensor
  - Fusion: concat(card_flat, action_flat, extra_fc) → shared trunk → policy + value heads

Based on: Zhao et al., "AlphaHoldem: High-Performance AI for HUNL Poker
via End-to-End RL", AAAI 2022.

V2: Scaled to ~8.6M params to match paper.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F


def _make_norm(kind: str, num_features: int) -> nn.Module:
    """Build a 2D normalization layer. kind ∈ {'bn', 'gn', 'ln'}.

    bn = BatchNorm2d (running stats; mode-dependent)
    gn = GroupNorm  (no running stats; mode-independent — recommended for long self-play)
    ln = GroupNorm(num_groups=1) (channel-wise LayerNorm equivalent for Conv2d)
    """
    if kind == 'bn':
        return nn.BatchNorm2d(num_features)
    if kind == 'gn':
        groups = 8
        while num_features % groups != 0 and groups > 1:
            groups -= 1
        return nn.GroupNorm(groups, num_features)
    if kind == 'ln':
        return nn.GroupNorm(1, num_features)
    raise ValueError(f'Unknown norm_layer: {kind!r} (expected bn/gn/ln)')


class ResBlock(nn.Module):
    """Residual block with optional stride for downsampling."""

    def __init__(self, in_channels: int, out_channels: int, stride: int = 1, norm_layer: str = 'bn'):
        super().__init__()
        self.conv1 = nn.Conv2d(in_channels, out_channels, 3, stride=stride, padding=1, bias=False)
        self.bn1 = _make_norm(norm_layer, out_channels)
        self.conv2 = nn.Conv2d(out_channels, out_channels, 3, stride=1, padding=1, bias=False)
        self.bn2 = _make_norm(norm_layer, out_channels)

        self.shortcut = nn.Sequential()
        if stride != 1 or in_channels != out_channels:
            self.shortcut = nn.Sequential(
                nn.Conv2d(in_channels, out_channels, 1, stride=stride, bias=False),
                _make_norm(norm_layer, out_channels),
            )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.bn2(self.conv2(out))
        out = out + self.shortcut(x)
        return F.relu(out)


class CNNBranch(nn.Module):
    """CNN encoder branch — scaled up to match paper's 1.8M conv params."""

    def __init__(self, in_channels: int, norm_layer: str = 'bn'):
        super().__init__()
        # Scaled: 48→96→192 with 2 res blocks each
        self.conv1 = nn.Conv2d(in_channels, 48, 3, stride=1, padding=1, bias=False)
        self.bn1 = _make_norm(norm_layer, 48)
        self.res1a = ResBlock(48, 96, stride=2, norm_layer=norm_layer)
        self.res1b = ResBlock(96, 96, norm_layer=norm_layer)
        self.res2a = ResBlock(96, 192, stride=2, norm_layer=norm_layer)
        self.res2b = ResBlock(192, 192, norm_layer=norm_layer)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = F.relu(self.bn1(self.conv1(x)))
        out = self.res1b(self.res1a(out))
        out = self.res2b(self.res2a(out))
        return out.flatten(start_dim=1)


CRITIC_V1 = "critic_v1"
CRITIC_V2 = "critic_v2"
H1_CRITIC_INIT_SEED = 2026071102

class AlphaHoldemNet(nn.Module):
    """
    AlphaHoldem pseudo-Siamese network (scaled).

    Inputs:
      card_info:   (B, 6, 4, 13)
      action_info: (B, 25, 4, 5)
      extra_info:  (B, 2), or (B, 3) when a position adapter is enabled

    Outputs:
      policy_logits: (B, num_actions)
      value:         (B, 1)
    """

    def __init__(
        self,
        num_actions: int = 9,
        norm_layer: str = 'bn',
        critic_contract: str = CRITIC_V1,
        critic_init_seed: int = H1_CRITIC_INIT_SEED,
        separate_preflop_head: bool = False,
        preflop_adapter_hidden: int = 0,
        preflop_raw_adapter_hidden: int = 0,
        flop_adapter_hidden: int = 0,
        postflop_adapter_hidden: int = 0,
        position_adapter_hidden: int = 0,
    ):
        super().__init__()
        if critic_contract not in {CRITIC_V1, CRITIC_V2}:
            raise ValueError(f"unknown critic_contract: {critic_contract}")
        self.num_actions = num_actions
        self.norm_layer = norm_layer
        self.critic_contract = critic_contract
        self.critic_init_seed = int(critic_init_seed)
        self.separate_preflop_head = bool(separate_preflop_head)
        self.preflop_adapter_hidden = int(preflop_adapter_hidden)
        self.preflop_raw_adapter_hidden = int(preflop_raw_adapter_hidden)
        self.flop_adapter_hidden = int(flop_adapter_hidden)
        self.postflop_adapter_hidden = int(postflop_adapter_hidden)
        self.position_adapter_hidden = int(position_adapter_hidden)

        self.card_cnn = CNNBranch(in_channels=6, norm_layer=norm_layer)
        self.action_cnn = CNNBranch(in_channels=25, norm_layer=norm_layer)

        self.extra_fc = nn.Sequential(
            nn.Linear(2, 32),
            nn.ReLU(),
        )

        # Trunk (lazy init)
        self.trunk = None
        self.policy_head = None
        self.preflop_policy_head = None
        self.preflop_policy_adapter = None
        self.preflop_raw_policy_adapter = None
        self.flop_policy_adapter = None
        self.postflop_policy_adapter = None
        self.position_policy_adapters = None
        self.value_head = None

    def _init_trunk(self, card_flat: int, action_flat: int):
        """Initialize trunk after first forward pass determines flat sizes."""
        fusion_dim = card_flat + action_flat + 32  # 32 from extra_fc
        # Paper: 6.8M FC params → need large trunk
        self.trunk = nn.Sequential(
            nn.Linear(fusion_dim, 2048),
            nn.ReLU(),
            nn.Linear(2048, 1024),
            nn.ReLU(),
            nn.Linear(1024, 512),
            nn.ReLU(),
            nn.Linear(512, 256),
            nn.ReLU(),
        )
        self.policy_head = nn.Linear(256, self.num_actions)
        if self.separate_preflop_head:
            self.preflop_policy_head = nn.Linear(256, self.num_actions)
        if self.preflop_adapter_hidden > 0:
            self.preflop_policy_adapter = nn.Sequential(
                nn.Linear(256, self.preflop_adapter_hidden),
                nn.ReLU(),
                nn.Linear(self.preflop_adapter_hidden, self.num_actions),
            )
            nn.init.zeros_(self.preflop_policy_adapter[-1].weight)
            nn.init.zeros_(self.preflop_policy_adapter[-1].bias)
        if self.preflop_raw_adapter_hidden > 0:
            raw_dim = 6 * 4 * 13 + 25 * 4 * 5 + 2
            self.preflop_raw_policy_adapter = nn.Sequential(
                nn.Linear(raw_dim, self.preflop_raw_adapter_hidden),
                nn.ReLU(),
                nn.Linear(
                    self.preflop_raw_adapter_hidden,
                    self.preflop_raw_adapter_hidden,
                ),
                nn.ReLU(),
                nn.Linear(self.preflop_raw_adapter_hidden, self.num_actions),
            )
            nn.init.zeros_(self.preflop_raw_policy_adapter[-1].weight)
            nn.init.zeros_(self.preflop_raw_policy_adapter[-1].bias)
        if self.flop_adapter_hidden > 0:
            self.flop_policy_adapter = nn.Sequential(
                nn.Linear(256, self.flop_adapter_hidden),
                nn.ReLU(),
                nn.Linear(self.flop_adapter_hidden, self.num_actions),
            )
            nn.init.zeros_(self.flop_policy_adapter[-1].weight)
            nn.init.zeros_(self.flop_policy_adapter[-1].bias)
        if self.postflop_adapter_hidden > 0:
            self.postflop_policy_adapter = nn.Sequential(
                nn.Linear(256, self.postflop_adapter_hidden),
                nn.ReLU(),
                nn.Linear(self.postflop_adapter_hidden, self.num_actions),
            )
            nn.init.zeros_(self.postflop_policy_adapter[-1].weight)
            nn.init.zeros_(self.postflop_policy_adapter[-1].bias)
        if self.position_adapter_hidden > 0:
            self.position_policy_adapters = nn.ModuleList(
                [
                    nn.Sequential(
                        nn.Linear(256, self.position_adapter_hidden),
                        nn.ReLU(),
                        nn.Linear(
                            self.position_adapter_hidden,
                            self.num_actions,
                        ),
                    )
                    for _ in range(2)
                ]
            )
            for adapter in self.position_policy_adapters:
                nn.init.zeros_(adapter[-1].weight)
                nn.init.zeros_(adapter[-1].bias)
        if self.critic_contract == CRITIC_V1:
            self.value_head = nn.Linear(256, 1)
        else:
            # Deterministic critic construction must not perturb actor/global RNG.
            with torch.random.fork_rng(devices=[]):
                torch.manual_seed(self.critic_init_seed)
                self.value_head = nn.Sequential(
                    nn.Linear(256, 256),
                    nn.ReLU(),
                    nn.Linear(256, 128),
                    nn.ReLU(),
                    nn.Linear(128, 1),
                )
                for layer in (self.value_head[0], self.value_head[2]):
                    nn.init.orthogonal_(layer.weight, gain=2 ** 0.5)
                    nn.init.zeros_(layer.bias)
                nn.init.orthogonal_(self.value_head[4].weight, gain=1.0)
                nn.init.zeros_(self.value_head[4].bias)

    def forward(
        self,
        card_info: torch.Tensor,
        action_info: torch.Tensor,
        extra_info: torch.Tensor,
        legal_mask: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        card_flat = self.card_cnn(card_info)
        action_flat = self.action_cnn(action_info)
        extra_flat = self.extra_fc(extra_info[:, :2])

        if self.trunk is None:
            self._init_trunk(card_flat.shape[1], action_flat.shape[1])
            device = card_info.device
            self.trunk = self.trunk.to(device)
            self.policy_head = self.policy_head.to(device)
            if self.preflop_policy_head is not None:
                self.preflop_policy_head = self.preflop_policy_head.to(device)
            if self.preflop_policy_adapter is not None:
                self.preflop_policy_adapter = self.preflop_policy_adapter.to(device)
            if self.preflop_raw_policy_adapter is not None:
                self.preflop_raw_policy_adapter = (
                    self.preflop_raw_policy_adapter.to(device)
                )
            if self.flop_policy_adapter is not None:
                self.flop_policy_adapter = self.flop_policy_adapter.to(device)
            if self.postflop_policy_adapter is not None:
                self.postflop_policy_adapter = self.postflop_policy_adapter.to(device)
            if self.position_policy_adapters is not None:
                self.position_policy_adapters = (
                    self.position_policy_adapters.to(device)
                )
            self.value_head = self.value_head.to(device)

        fused = torch.cat([card_flat, action_flat, extra_flat], dim=1)
        h = self.trunk(fused)

        policy_logits = self.policy_head(h)
        if self.preflop_policy_head is not None:
            # The teacher loss must not rewrite shared postflop features. The
            # dedicated head learns on a detached view; postflop PPO continues
            # through the original policy head and trunk.
            preflop_logits = self.preflop_policy_head(h.detach())
            if self.preflop_policy_adapter is not None:
                preflop_logits = (
                    preflop_logits + self.preflop_policy_adapter(h.detach())
                )
            if self.preflop_raw_policy_adapter is not None:
                raw_preflop = torch.cat(
                    [
                        card_info.flatten(start_dim=1),
                        action_info.flatten(start_dim=1),
                        extra_info[:, :2],
                    ],
                    dim=1,
                )
                preflop_logits = (
                    preflop_logits
                    + self.preflop_raw_policy_adapter(raw_preflop)
                )
            is_preflop = card_info[:, 4].sum(dim=(1, 2)) <= 1e-6
            policy_logits = torch.where(
                is_preflop.unsqueeze(-1),
                preflop_logits,
                policy_logits,
            )
        if self.flop_policy_adapter is not None:
            flop_logits = policy_logits + self.flop_policy_adapter(h.detach())
            board_count = card_info[:, 4].sum(dim=(1, 2))
            is_flop = (board_count >= 2.5) & (board_count < 3.5)
            policy_logits = torch.where(
                is_flop.unsqueeze(-1),
                flop_logits,
                policy_logits,
            )
        if self.postflop_policy_adapter is not None:
            postflop_logits = policy_logits + self.postflop_policy_adapter(h.detach())
            board_count = card_info[:, 4].sum(dim=(1, 2))
            is_postflop = board_count >= 2.5
            policy_logits = torch.where(
                is_postflop.unsqueeze(-1),
                postflop_logits,
                policy_logits,
            )
        if self.position_policy_adapters is not None:
            if extra_info.shape[1] < 3:
                raise ValueError(
                    'position_policy_adapters require extra_info[:, 2] seat '
                    'feature'
                )
            seat = extra_info[:, 2].round().long().clamp(0, 1)
            seat_deltas = torch.stack(
                [
                    adapter(h.detach())
                    for adapter in self.position_policy_adapters
                ],
                dim=1,
            )
            selected_delta = seat_deltas.gather(
                1,
                seat.view(-1, 1, 1).expand(-1, 1, self.num_actions),
            ).squeeze(1)
            policy_logits = policy_logits + selected_delta
        value_input = h.detach() if self.critic_contract == CRITIC_V2 else h
        value = self.value_head(value_input)

        if legal_mask is not None:
            policy_logits = policy_logits + (1 - legal_mask) * (-1e9)

        return policy_logits, value


def count_parameters(model: nn.Module) -> int:
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


if __name__ == '__main__':
    net = AlphaHoldemNet(num_actions=9)
    B = 4
    card = torch.randn(B, 6, 4, 13)
    action = torch.randn(B, 25, 4, 5)
    extra = torch.randn(B, 2)
    mask = torch.ones(B, 9)

    logits, val = net(card, action, extra, mask)
    print(f'Policy logits: {logits.shape}')
    print(f'Value: {val.shape}')
    print(f'Parameters: {count_parameters(net):,}')

    # Breakdown
    conv_params = sum(p.numel() for n, p in net.named_parameters() if 'cnn' in n)
    fc_params = sum(p.numel() for n, p in net.named_parameters() if 'trunk' in n or 'head' in n or 'extra' in n)
    print(f'Conv params: {conv_params:,}')
    print(f'FC params:   {fc_params:,}')
