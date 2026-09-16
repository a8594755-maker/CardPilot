$ErrorActionPreference = 'Stop'

$experiment = 'research/experiments/v6-static-current-kl-1m-scale-20260903'
$parentExperiment = 'research/experiments/v6-static-current-kl-262k-scale-20260903'
$standard10 = 'models/baseline/standard10/latest.pt'
$standard10Sha = '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
$anchor2 = 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/slumbot_free_anchor_position10m.pt'
$anchor3 = 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/corrected_cfr96_anchor10.pt'

$seeds = @(
    @{ Name='seed1'; Seed=20263001; WorkerSeed=2026300100; DealStart=30300000; RunId='v6_nashpg_static_seed1_20260903'; CheckpointSha='1e9cda7fb9793554d767f36957df9c730baab32e1d2cd5f972497ab25d044e43'; MetricsSha='ec8e33c3768265f3f7276dd4e97d466913905c7d773894f1f8ab1f2a9b443a28'; AssignmentSha='9bf8b23805ecfd17ccf46ba18df7123b4c2bd90f207735216668ab07ff2cff32' },
    @{ Name='seed2'; Seed=20263002; WorkerSeed=2026300200; DealStart=31300000; RunId='v6_nashpg_static_seed2_20260903'; CheckpointSha='2ac666344ad73b6d4a3a36cdfffed0e5f5cc9b4c8c40b7dc6227a5fc6803d8d6'; MetricsSha='49c3faa0e0956a349908976296912b2600311794e9a603b0e37507edb8b56f2b'; AssignmentSha='8458e3f0320effab2511d29572b06d36bfcc6588450acf1a0bda5e2d4366af06' },
    @{ Name='seed3'; Seed=20263003; WorkerSeed=2026300300; DealStart=32300000; RunId='v6_nashpg_static_seed3_20260903'; CheckpointSha='ce9a7ad4769cb1fca56231239866f7a478eef9958416ca53cf8c3e03c6f1c236'; MetricsSha='ca4bf5dbfe39106226c5cbfa56dbdc59f8456e6ce5d7566b85fa3c9eb0bfe7db'; AssignmentSha='3f489ca0c416f7870c294d32fa4e9b06d8a9d21c07cf7db6c6ed7d3aa8c9843e' }
)

if ((Get-FileHash -Algorithm SHA256 -LiteralPath $standard10).Hash.ToLower() -ne $standard10Sha) {
    throw 'Standard10 SHA256 mismatch'
}
foreach ($required in @($anchor2, $anchor3)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Missing immutable opponent: $required"
    }
}

python -m pytest -q `
    scripts/alpha_holdem/test_train_v5_dynamic_pool.py `
    scripts/alpha_holdem/test_train_v5_replay.py `
    scripts/alpha_holdem/test_source_policy_moving_reference.py `
    scripts/alpha_holdem/test_source_policy_kl_temperature.py `
    scripts/alpha_holdem/test_ppo_gradient_update_equivalence.py
if ($LASTEXITCODE -ne 0) { throw 'Continuation preflight tests failed' }

python scripts/alpha_holdem/stage_v6_integrated_scale_resume.py `
    --source "seed1=$parentExperiment/seed1" `
    --source "seed2=$parentExperiment/seed2" `
    --source "seed3=$parentExperiment/seed3" `
    --deal-start seed1=30300000 `
    --deal-start seed2=31300000 `
    --deal-start seed3=32300000 `
    --out-dir $experiment `
    --manifest-name resume_stage_manifest.json
if ($LASTEXITCODE -ne 0) { throw 'Exact-state resume staging failed' }

foreach ($seedInfo in $seeds) {
    $parentDir = "$parentExperiment/$($seedInfo.Name)"
    $parentCheckpoint = "$parentDir/latest.pt"
    $runDir = "$experiment/$($seedInfo.Name)"
    $out = "$runDir/latest.pt"
    $assignment = "$runDir/opponent_assignments.jsonl"
    $metrics = "$runDir/h1_training_metrics.jsonl"
    if (-not (Test-Path -LiteralPath $runDir -PathType Container)) {
        throw "Missing audited continuation run directory: $runDir"
    }
    if (Test-Path -LiteralPath $out) {
        throw "Refusing to overwrite continuation checkpoint: $out"
    }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $parentCheckpoint).Hash.ToLower() -ne $seedInfo.CheckpointSha) {
        throw "Parent checkpoint SHA256 mismatch for $($seedInfo.Name)"
    }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $metrics).Hash.ToLower() -ne $seedInfo.MetricsSha) {
        throw "Staged metric prefix mismatch for $($seedInfo.Name)"
    }
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $assignment).Hash.ToLower() -ne $seedInfo.AssignmentSha) {
        throw "Staged assignment prefix mismatch for $($seedInfo.Name)"
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
        '--worker-seed-base', [string]$seedInfo.WorkerSeed,
        '--fixed-training-deal-stream',
        '--fixed-training-deal-start-index', [string]$seedInfo.DealStart,
        '--critic-contract', 'critic_v2',
        '--h1-effective-stack-divisor', '200',
        '--h1-critic-init-seed', '2026071102',
        '--value-coef', '1',
        '--autonomous-critic-v2-continue',
        '--snapshot-every', '2',
        '--save-interval', '1',
        '--archive-checkpoint-every', '64',
        '--run-id', $seedInfo.RunId,
        '--run-dir', $runDir,
        '--out', $out,
        '--seed', [string]$seedInfo.Seed,
        '--max-runtime-seconds', '7200',
        '--resume', $parentCheckpoint,
        '--allow-resume',
        '--no-reset-optimizer',
        '--preserve-resumed-optimizer-lr',
        '--validate-stream'
    )
    Write-Host "Continuing static current-KL $($seedInfo.Name) to 1M"
    & python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$($seedInfo.Name) continuation failed with exit code $LASTEXITCODE"
    }
}
