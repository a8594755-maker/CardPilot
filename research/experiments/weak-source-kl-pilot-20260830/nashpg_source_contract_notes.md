# Conditional implementation notes from pinned upstream source

Read-only research during the existing weak-KL arm, before this pilot's matrix.
No upstream code was installed or executed, no current training source was
edited, and no additional poker hands were generated. This is not a new
experiment or a replacement for the registered confirmation branch on success.

## Source identity and observed behavior

GitHub's main commit resolved to
`dda50fe112f2d5bbbc46af33c8f1550e0177cc29` (2026-08-02T07:55:10Z).
All source links below are pinned to that commit.

- The training loop samples current-policy self-play, trains on both players,
  retains its optimizer, and clones the updated agent into the reference after
  each outer round's inner updates.
  [Training loop, lines151-188](https://github.com/ntu-agents/nashpg/blob/dda50fe112f2d5bbbc46af33c8f1550e0177cc29/train/nash_pg.py#L151-L188)
- The actor objective adds categorical KL(current || reference) on valid
  observations, alongside PPO and entropy; the reference is not optimized.
  Critic targets are separate from this direct regularization term.
  [Loss, lines54-104](https://github.com/ntu-agents/nashpg/blob/dda50fe112f2d5bbbc46af33c8f1550e0177cc29/train/core/update_agent.py#L54-L104)
- The data path uses player-indexed reward accumulation and GAE. A single agent
  supplies both seats unless an explicit list is supplied.
  [Trajectory and GAE implementation](https://github.com/ntu-agents/nashpg/blob/dda50fe112f2d5bbbc46af33c8f1550e0177cc29/train/core/prepare_data.py)
- BaseAgent.save_checkpoint saves the agent state. It does not itself save the
  learner's optimizer, reference, random key, environment state or round counters.
  [Checkpoint API, lines71-88](https://github.com/ntu-agents/nashpg/blob/dda50fe112f2d5bbbc46af33c8f1550e0177cc29/agents/base_agent.py#L71-L88)
- Repository defaults include entropy0.05, 32environments x128steps, KL0.2,
  1000inner updates and50outer rounds. These are repository defaults, not proof
  of the exact configuration used for every paper result; they differ from some
  paper-table entries. Do not silently combine them.
  [Algorithm defaults](https://github.com/ntu-agents/nashpg/blob/dda50fe112f2d5bbbc46af33c8f1550e0177cc29/conf/algorithm/nash_pg.yaml)
- The published poker agent has separate policy and critic feature extractors.
  Replacing our shared/frozen representation with it would be an additional
  architecture intervention, not merely a regularization change.
  [Poker agent, lines118-132](https://github.com/ntu-agents/nashpg/blob/dda50fe112f2d5bbbc46af33c8f1550e0177cc29/agents/poker.py#L118-L132)

## Local engineering proposal, not an executed method

If the present pilot is not admitted, first preregister a separate implementation
contract. Port mathematical semantics into the local PyTorch path instead of
assuming an upstream agent checkpoint is a lossless local training checkpoint.
Keep the current legacy reverse-direction objective as the default. Introduce
explicit opt-in names for KL direction and reference-refresh interval; labels
must distinguish a NashPG-inspired local variant from a faithful reproduction.

For categorical current probabilities p and reference q on an identical legal
support, test `D=sum(p*(log(p)-log(q)))`. The analytic logit gradient is
`p*(log(p)-log(q)-D)`. This differs from the legacy reference-to-current gradient
`p-q`. Check asymmetric distributions and finite differences; equality at p=q
alone cannot distinguish the two objectives. Reference probabilities must be
detached, illegal actions excluded before all reductions, and empty legal rows
rejected. Test singleton legal support and extreme finite legal logits without
introducing probability-floor mass on illegal slots.

Define refresh at a completed PPO-update boundary, not after an arbitrary Adam
minibatch or a wall-clock interval. Initial reference is the initialized policy;
after each preregistered K completed PPO updates, copy the post-update policy,
then persist the complete checkpoint before the next collection. The checkpoint
must include reference weights, total completed PPO updates, last refresh update,
reference round, interval/direction, optimizer and existing RNG/physical-hand/
assignment state. Restore must validate their consistency and never silently
rebuild reference weights from the current policy. Test before, exactly at, and
after a refresh boundary, including no double refresh after restoration.

Keep stateful-training-resume tests distinct from pure loss tests. Contract
fixtures contribute zero 200bb environment hands. A subsequent physical-budget
pilot should change static versus refreshed reference only, at a shared KL
direction, coefficient, parameter scope and sampling regime. Using pure current
self-play in that new pilot is not equivalent to this experiment's 25%self-play
adaptive fixed-anchor mixture; report that difference rather than reusing the
present control as if matched. Do not reset the optimizer at reference refresh.

These tests would establish mechanics, not convergence, general strength or the
100000-fresh-hand Slumbot goal. The original conditional_next_direction.md and
current preregistration still determine the next branch after the fixed matrix.
