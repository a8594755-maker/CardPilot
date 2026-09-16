# V6 contract repair validated

Final frozen-source validation:4096 hands, 34159 decisions, 88 passing tests. Integer-chip transitions match independent PokerKit0.7.5; every decision matches external-prefix reconstruction, and canonical history/cards match independent client encoders. BB option, full minimum raises, short all-ins, no raise cap, chip conservation, zero-sum terminal payoff and history overflow tested.

Raw event/hand evidence aligns exactly; 71 source/copy pairs and 8 oracle source hashes verified. Five legacy runtime files and three frozen policies remain unchanged. Trainer changes are explicit v6 branches; new v6 mirror and deployment use the same inference/action contract.

core01 and final01 reuse the same4096 fixed deals:8192 executed validation trajectories, not8192 independent samples. Pytest fixtures are synthetic/regression checks, not strength data. Training/evaluation/Slumbot accounting is zero. Development failure reports01(card formatting) and03(test import path) are retained alongside passes02/04/05.

Next: separately preregister a small measured-physical-hand v6 trainer smoke, verify actual optimizer/checkpoint/worker accounting, then establish corrected-environment frozen multi-anchor baselines and a learned-weight curve. No positive-strength claim or100k admission follows from infrastructure tests. Legacy ELO and unversioned offline replay remain blocked pending their own v6 contracts.
