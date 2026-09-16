# Exact-v6 neural regret optimizer dose control

Decision: `ADMIT_SELECTED_OPTIMIZER_DOSE`; selected dose: 128 steps.

Before corpus generation, implementation audit established that the preceding
smoke had zeroed the full ReLU network. This control preserved seeded random
hidden features and made only the final output projection exactly passive. The
eight frozen exact-v6 roots produced 1,336 targets per seat, split once into
1,069 training and 267 held-out samples. All arms share the corpus hash
`b5d0fa94b22486befdca81510f6ffbd951b7fcda69ecc6e998884f776e64dc47`
and initial-weight hash
`1ee054391742ff0f821b524379f59aa522e03516a93b83b5aeeac927847be3ac`.

At 32 steps, held-out loss fell only 6.68%/6.60%, although live hidden features
already enabled 25.1%/35.2% argmax movement. At 128 steps, held-out loss fell
35.23%/33.47% and argmax movement reached 25.1%/47.9%; both seats passed the
preregistered 20%-loss and 5%-movement gates. The 512-step arm fit more strongly
(81.09%/75.24% loss reduction), but the outcome-blind selection rule chooses the
lowest passing dose, 128.

The asymmetric player-1 movement exceeds the fraction of held-out target
argmaxes that differ from passive, so this remains a small, correlated target
corpus rather than proof of generalization. The next iterative pilot should use
128 steps, serialize optimizer and buffers for exact resume, track node growth,
and evaluate only frozen iteration checkpoints on a separate multi-anchor deck
panel. Scaling should require a coherent learning curve, not merely target fit.
