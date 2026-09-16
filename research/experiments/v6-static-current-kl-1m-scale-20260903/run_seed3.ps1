$ErrorActionPreference = 'Stop'

$experiment = 'research/experiments/v6-static-current-kl-1m-scale-20260903'
$parentExperiment = 'research/experiments/v6-static-current-kl-262k-scale-20260903'
$standard10 = 'models/baseline/standard10/latest.pt'
$standard10Sha = '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
$anchor2 = 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/slumbot_free_anchor_position10m.pt'
$anchor3 = 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/corrected_cfr96_anchor10.pt'
$parentCheckpoint = "$parentExperiment/seed3/latest.pt"
$parentCheckpointSha = 'ce9a7ad4769cb1fca56231239866f7a478eef9958416ca53cf8c3e03c6f1c236'
$runDir = "$experiment/seed3"
$out = "$runDir/latest.pt"
$metrics = "$runDir/h1_training_metrics.jsonl"
$metricsSha = 'ca4bf5dbfe39106226c5cbfa56dbdc59f8456e6ce5d7566b85fa3c9eb0bfe7db'
$assignment = "$runDir/opponent_assignments.jsonl"
$assignmentSha = '3f489ca0c416f7870c294d32fa4e9b06d8a9d21c07cf7db6c6ed7d3aa8c9843e'

if ((Get-FileHash -Algorithm SHA256 -LiteralPath $standard10).Hash.ToLower() -ne $standard10Sha) {
    throw 'Standard10 SHA256 mismatch'
}
foreach ($required in @($anchor2, $anchor3)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing immutable opponent: $required"
    }
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $parentCheckpoint).Hash.ToLower() -ne $parentCheckpointSha) {
    throw 'Seed3 parent checkpoint SHA256 mismatch'
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $metrics).Hash.ToLower() -ne $metricsSha) {
    throw 'Seed3 staged metric prefix mismatch'
}
if ((Get-FileHash -Algorithm SHA256 -LiteralPath $assignment).Hash.ToLower() -ne $assignmentSha) {
    throw 'Seed3 staged assignment prefix mismatch'
}
if (Test-Path -LiteralPath $out -PathType Leaf) {
    throw "Refusing to overwrite seed3 continuation checkpoint: $out"
}

$arguments = @(
    '-u', 'scripts/alpha_holdem/train_v5.py',
    '--device', 'cuda',
    '--workers', '12',
    '--hands-per-iter', '4096',
    '--total-hands', '99999999',
    '--total-environment-hands', '1048576',
    '--starting-stack', '200',
    '--env-version', 'v6legacyv4obs',
    '--norm-layer', 'gn',
    '--lr', '0.0003',
    '--ppo-epochs', '2',
    '--ppo-target-kl', '0.01',
    '--policy-advantage-clip', '3',
    '--source-policy-kl-coef', '1',
    '--source-policy-kl-direction', 'current_to_reference',
    '--source-policy-reference-checkpoint', $standard10,
    '--separate-preflop-head',
    '--all-policy-heads-only-training',
    '--mini-batch-size', '16384',
    '--entropy-coef', '0.005',
    '--entropy-floor', '0.05',
    '--ppo-replay-buffer-iterations', '2',
    '--ppo-replay-ratio', '0.5',
    '--k-best', '5',
    '--pool-strategy', 'loss-kbest',
    '--initial-opponent-checkpoints', $standard10, $anchor2, $anchor3,
    '--hero-policy-mode', 'sample',
    '--self-play-fraction', '0.25',
    '--opponent-assignment', 'per-group',
    '--opponent-groups', '8',
    '--adaptive-opponent-league',
    '--adaptive-league-ema', '0.9',
    '--adaptive-league-temperature-bb', '2',
    '--adaptive-league-min-probability', '0.05',
    '--opponent-assignment-provenance-file', $assignment,
    '--resume-assignment-state-from-provenance',
    '--rollout-mode', 'single',
    '--rollout-envs-per-worker', '1',
    '--inference-min-batch-slots', '0',
    '--inference-batch-deadline-us', '700',
    '--worker-seed-base', '2026300300',
    '--fixed-training-deal-stream',
    '--fixed-training-deal-start-index', '32300000',
    '--critic-contract', 'critic_v2',
    '--h1-effective-stack-divisor', '200',
    '--h1-critic-init-seed', '2026071102',
    '--value-coef', '1',
    '--autonomous-critic-v2-continue',
    '--snapshot-every', '2',
    '--save-interval', '1',
    '--archive-checkpoint-every', '64',
    '--run-id', 'v6_nashpg_static_seed3_20260903',
    '--run-dir', $runDir,
    '--out', $out,
    '--seed', '20263003',
    '--max-runtime-seconds', '7200',
    '--resume', $parentCheckpoint,
    '--allow-resume',
    '--no-reset-optimizer',
    '--preserve-resumed-optimizer-lr',
    '--validate-stream'
)
Write-Host 'Continuing static current-KL seed3 to 1M'
& python @arguments
if ($LASTEXITCODE -ne 0) {
    throw "Seed3 continuation failed with exit code $LASTEXITCODE"
}
