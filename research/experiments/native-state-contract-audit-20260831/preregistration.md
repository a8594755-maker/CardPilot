# Native training / mirror / Slumbot contract audit

Registered after the completed full-network20k pilot scored-81.251bb/100,
95%CI[-123.160,-39.342], despite broad positive internal replication. Existing
raw hands, checkpoints, records and executed sources remain unchanged.

Static source inspection identified plausible execution-contract discrepancies;
these are not yet a quantified causal explanation of the external loss. Test
five fixed deterministic probes using captured, unchanged production sources:

1. At the posted200bb blinds, compare action masks and physical slot targets for
   the actual trainer v55preflopv2v4obs configuration, the actual mirror default
   environment/observation path, and Slumbot's checkpoint-owned mapping.
2. Apply the trainer root check/call slot once and compare street/actor/board to
   Slumbot parsing the first SB completion, prefix c. No further action.
3. At a constructed, physically consistent limp-check flop, pot2bb,stacks199bb,
   compare legal opening bets with Slumbot prefix ck/. This isolates the legal
   table from the already suspected preflop-transition discrepancy.
4. At that same flop after a legal3bb opening bet, compare minimum re-raise
   targets with Slumbot prefix ck/b300. Keep chip rounding differences explicit.
5. At that same flop after the native all-in slot, compare v4 action-history
   tensors with Slumbot prefix ck/b19900, where physical public state matches.

Use one deterministic legal card fixture; these are interface probes, not a
representative sample of poker strategy. No complete hands, training, policy
optimization, external requests, benchmark re-evaluation or score-based choice.
Reject accidental terminal states and network calls. Capture helper, production
sources, copies, hashes and dirty patch before the probes; verify them after.
No source fixes inside this diagnostic run and no automatic overwrite/rerun.

Report each observed discrepancy, not merely an aggregate pass label. Any
discrepancy prioritizes a separately recorded contract/rules repair before more
learned-weight scaling. No discrepancy means only these five probes matched;
it does not establish full equivalence. Do not rewrite historical raw evidence
or claim that a mismatch quantitatively explains-81.251bb/100. Any historical
interpretation correction must be a separate explicit addendum.

The original goal still requires a single frozen learned policy with at least
100000fresh Slumbot hands,positive bb/100 and a positive95%CI lower bound.
