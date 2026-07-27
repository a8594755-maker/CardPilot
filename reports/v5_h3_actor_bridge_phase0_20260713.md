# H3 actor bridge phase 0

`PHASE0_ACTION_BRIDGE_PASS_OBSERVATION_AND_ASSET_GATES_PENDING`.

The corrected converter now reproduces every action list in a compact corrected HU tree and maps CFR policy mass exactly into AlphaHoldem's nine action slots. It no longer invents raises after an opponent all-in and respects stack/raise-cap action pruning.

This is not a complete H3 bridge. Exact v55 `card_info`, `action_info`, `extra_info`, and `legal_mask` reconstruction is still missing, and the corrected successor has not yet completed its 600-board gate. No critic supervision, H3 preregistration, behavior launch, official hands, or strength claim is authorized.
