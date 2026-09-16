# Held-out learned-policy proxy ranking panel

The original five adaptive-league opponents promoted two continuation tails
that then failed independent greedy Slumbot pilots.  Construct an offline panel
of five frozen learned policies that did not participate in the raw actor's
training league: entropy-penalty treatment, causal-TCN treatment, centralized-
critic treatment, full-network 265k final, and physical1m final.

Evaluate three frozen candidates under generic greedy execution: parent
(`9fd38ad3...`, external fresh5k -9.4188), parent-KL (`1c050edb...`, -65.5040),
and weak-KL tail (`6f3bf544...`, -91.0228).  Run 512 mirrored pairs per cell
with common seed 20261104.  These external points define only a fixed ordinal
validation target and are not pooled or used as training labels.

Call the panel useful only if paired panel-average parent-minus-parent-KL and
parent-minus-weak-tail means both have 95% CI lower bounds above zero, and parent
beats each tail pointwise on at least 3/5 opponents.  Otherwise discard the panel
as another unreliable proxy.  Zero network calls, training hands, or Slumbot
hands are allowed.

