$ErrorActionPreference = 'Stop'

$experiment = 'research/experiments/v6-static-current-kl-262k-scale-20260903'
$parentExperiment = 'research/experiments/v6-nashpg-moving-reference-geometric-20260903'
$standard10 = 'models/baseline/standard10/latest.pt'
$standard10Sha = '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
$anchor2 = 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/slumbot_free_anchor_position10m.pt'
$anchor3 = 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/corrected_cfr96_anchor10.pt'

$seeds = @(
    @{ Name='seed1'; Seed=20263001; WorkerSeed=2026300100; DealStart=30100000; RunId='v6_nashpg_static_seed1_20260903'; CheckpointSha='8b92b254396156d3e65833725e03b2f5ba30ae6aa9906c688b15aa5b856c8238'; MetricsSha='a7c8ca7ceeb11ffc363a3fca02ef151858ad8706293f49b99596549d2fbc32dc'; AssignmentSha='c3e8806da22fe4e603ba427a65c935ecfa78b5ad74c02387370a70520b011cc3' },
    @{ Name='seed2'; Seed=20263002; WorkerSeed=2026300200; DealStart=31100000; RunId='v6_nashpg_static_seed2_20260903'; CheckpointSha='690c2e9e614b8f7f86408c0d8142dd7d3b3a42dcda31df79107068197be658a7'; MetricsSha='c20a0d3f0a285c3980412fc118460b3301eaa653f685df056becda8ec3d3cc7d'; AssignmentSha='ff60bb8c91276c7ed8c7efa0d93efbc414917fe3b6a292a1fc056ac8cc1f46de' },
    @{ Name='seed3'; Seed=20263003; WorkerSeed=2026300300; DealStart=32100000; RunId='v6_nashpg_static_seed3_20260903'; CheckpointSha='ba6effa3ca20cccf371eef6d0ee80f93f7334e2622bc04920c932493d4ec3af9'; MetricsSha='8503bbe2b2eae765565f9a7a3e3e730a97c5a919dd92d196467b298a5f376d84'; AssignmentSha='6bc27d50b8180ffdf6a076cce7657d018de81eac5da9a62a3bf2776279e2a55e' }
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
    scripts/alpha_holdem/test_source_policy_moving_reference.py `
    scripts/alpha_holdem/test_source_policy_kl_temperature.py `
    scripts/alpha_holdem/test_ppo_gradient_update_equivalence.py
if ($LASTEXITCODE -ne 0) { throw 'Continuation preflight tests failed' }

python scripts/alpha_holdem/stage_v6_integrated_scale_resume.py `
    --source "seed1=$parentExperiment/static_seed1" `
    --source "seed2=$parentExperiment/static_seed2" `
    --source "seed3=$parentExperiment/static_seed3" `
    --deal-start seed1=30100000 `
    --deal-start seed2=31100000 `
    --deal-start seed3=32100000 `
    --out-dir $experiment `
    --manifest-name resume_stage_manifest.json
if ($LASTEXITCODE -ne 0) { throw 'Exact-state resume staging failed' }

foreach ($seedInfo in $seeds) {
    $parentDir = "$parentExperiment/static_$($seedInfo.Name)"
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
        '--total-environment-hands', '262144',
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
        '--archive-checkpoint-every', '16',
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
    Write-Host "Continuing static current-KL $($seedInfo.Name)"
    & python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$($seedInfo.Name) continuation failed with exit code $LASTEXITCODE"
    }
}
