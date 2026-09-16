# Slumbot public opponent-model feasibility analysis

The recovery parsed all 20,000 audited Standard10-bridge hands from eight
independent sessions and reconstructed 58,338 Slumbot decisions.  Fourteen
all-in showdown histories used trailing runout separators after the betting
state was already terminal; the initial strict parser rejected them.  The
recovery permits only separators after terminal and then achieved zero replay
failures.  The original failed artifacts remain in `run/`; accepted artifacts
are in `run_recovery/`.

The physical-v6 abstraction is adequate for an opponent model: 99.8594% of
observed actions exactly matched a legal slot and 99.9006% were within 0.10 pot
of the nearest legal slot.  Median and 95th-percentile sizing error were both
zero.  Every feature row masked the bot private-combo feature to `-1`; neither
showdown cards nor outcomes were used as labels.

The split was by complete network sessions, not random rows.  A 56x128x128x9
public-state model trained on s01--s06 and evaluated on untouched s07--s08
reduced NLL from the street-frequency baseline's 1.04882 to 0.69192 (34.03%)
and raised accuracy from 53.91% to 68.77% (+14.86 points).  This is strong
evidence that the behavior distribution is session-stable and state
conditioned.

Decision: `ADMIT_PUBLIC_OPPONENT_MODEL_CONTRACT_SMOKE`.  The artifact is not a
hero policy and the negative historical single-imitation result remains in
force.  The next test may load this model only as one bounded opponent in a
diverse fixed league, must verify exact legal sampling and replay, and must not
use Slumbot outcomes or allocate fresh Slumbot hands.
