# Same-checkpoint generic-greedy fresh5k Slumbot control

The raw actor failed 5,000 fresh strict-sampled hands at -79.2126 bb/100.
Offline replay on all 15,056 preserved decision states found only diffuse drift
from Standard10 (overall TV 0.0573, greedy disagreement 6.62%), so no localized
policy correction is justified.  Historical Standard10 evidence instead shows
a large general execution-contract gap: greedy -11.4275 versus strict sampled
-48.9778 bb/100.  Test that mechanism on the exact same raw learned weights.

Add a generic `greedy` mode to the v6 learned-only execution, journal, and audit
contracts while preserving strict-sampled defaults and behavior.  Greedy means
deterministic argmax over legal learned logits, behavior probability one-hot,
no heuristics, guards, action overrides, opponent-specific rules, or weight
changes.  Continue consuming and journaling the seeded uniform stream solely for
replay/accounting consistency; it must not affect greedy actions.  Unit tests
must prove legal argmax, deterministic uniform invariance, sample compatibility,
metadata integrity, and audit tamper rejection before any live hand.

Freeze raw checkpoint SHA256
9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4
and the captured runtime.  Run exactly eight new independent greedy sessions of
625 hands, seeds 2026104501..2026104508, with unique session IDs and no retry,
replacement, continuation, score stopping, endpoint change, or autoextension.
Require 5,000 durable raw hands, complete terminal/server-counter/model-decision
replay, and token-chain independence from the earlier sampled cohort and all
discoverable prior audits.  Independently compute raw-hand and session-t7 CIs.

Admit a separate fresh20k greedy confirmation only if aggregate bb/100 is
positive, at least 4/8 session means are positive, and the point estimate exceeds
the prior same-checkpoint sampled pilot by at least 20 bb/100.  These pilot hands
are not qualification hands and cannot be pooled into a later 100k proof.
