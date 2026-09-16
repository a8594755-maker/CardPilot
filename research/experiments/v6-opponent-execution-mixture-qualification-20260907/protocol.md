# Generic opponent execution-mixture qualification

Hypothesis: all historical opponents in current shared inference sample at T1,
while retained internal anchors execute greedily. Pool turnover alone did not
produce replicated own-parent gains. Broadening execution styles may train
robust responses without adding opponents derived from Slumbot labels.

Treatment is 0.5 times the original masked categorical distribution plus 0.5
times its legal first-argmax one-hot action, per decision. Hero sampling, hero
old log-probabilities, PPO objective, self-play hero requests, checkpoint weights,
opponent identity allocation, reference KL and all training counters stay unchanged.
This is not a claim that greedy is optimal or that sampled opponents are a bug.
Prior hero-temperature, source-KL-temperature and greedy-margin experiments do
not test this intervention. No benchmark-specific action rule is introduced.

This record qualifies only isolated distribution math and actual shared-inference
role isolation. It uses synthetic observation arrays, not new poker hands. It
does NOT establish worker rollout/resume integration or strength. Before training,
bind the wrapper, mixture setting and parent hashes in a managed attempt manifest,
check optimizer/replay/counters and actual opponent requests on both retained seeds.
The setting is experiment-runtime state and is not automatically embedded in the
frozen trainer's checkpoint metadata; fail-closed launch/resume binding is required.
No standalone --resume invocation should assume it restores this setting.

No external Slumbot hands are allocated. Training allocation follows successful
real resume qualification; a current matched control must retain weight zero.
