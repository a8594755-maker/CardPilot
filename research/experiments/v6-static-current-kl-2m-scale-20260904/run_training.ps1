$ErrorActionPreference = 'Stop'

$experiment = 'research/experiments/v6-static-current-kl-2m-scale-20260904'
$parentExperiment = 'research/experiments/v6-static-current-kl-1m-scale-20260903'
$standard10 = 'models/baseline/standard10/latest.pt'
$standard10Sha = '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
$anchor2 = 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/slumbot_free_anchor_position10m.pt'
$anchor3 = 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/corrected_cfr96_anchor10.pt'
$targetPhysicalHands = 2097152

$seeds = @(
    @{ Name='seed1'; Seed=20263001; WorkerSeed=2026300100; DealStart=33300000; RunId='v6_nashpg_static_seed1_20260903'; CheckpointSha='1fdc7ebc2560888938cc55bbf6c9eef05deb2e5c9270fbebb123d3143357dbe3'; MetricsSha='43f339c7b17d6aac4fb68fdc4e3a07f45d7693be04f4d1c2b2522973985cbf49'; AssignmentSha='9829229731c2774db26ab05160136f5feeb5ae74f0fefca9050c63d7820cb2a4' },
    @{ Name='seed2'; Seed=20263002; WorkerSeed=2026300200; DealStart=34300000; RunId='v6_nashpg_static_seed2_20260903'; CheckpointSha='d17081e1d611f9c1bbc4129c715211780d2c8e1f48519c8699b071481a85e27c'; MetricsSha='547e91b250227df4390f7b8544d31490ad847f545fe3adc7e30da2cc08b430ce'; AssignmentSha='9bced151ef1448a137a08871413feef92819c60f8f8b9515f43feb434aee6e83' },
    @{ Name='seed3'; Seed=20263003; WorkerSeed=2026300300; DealStart=35300000; RunId='v6_nashpg_static_seed3_20260903'; CheckpointSha='9c3235d2254d923103730310946b1c23be3e3122068f68bdc9e6273554bd9ee5'; MetricsSha='aadf4bfa9198f6801d875b124ac3877067b5236de125bbe6b1c7e3d39146820d'; AssignmentSha='f04a8941452710e6da539fdbb30135b1b44594f20dcc45e06c66d0a1048a3af0' }
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
    --deal-start seed1=33300000 `
    --deal-start seed2=34300000 `
    --deal-start seed3=35300000 `
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
        '--total-environment-hands', [string]$targetPhysicalHands,
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
    Write-Host "Continuing static current-KL $($seedInfo.Name) to 2M"
    # train_v5 owns latest_train.log. Do not pipe through Tee-Object on Windows:
    # holding a second writer open prevents the trainer from appending at the
    # first completed update boundary.
    & python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$($seedInfo.Name) continuation failed with exit code $LASTEXITCODE"
    }
    $physical = [int64](& python -c "import torch; print(int(torch.load(r'$out',map_location='cpu',weights_only=False)['environment_hand_accounting']['completed_hands']))")
    if ($physical -lt $targetPhysicalHands) {
        throw "$($seedInfo.Name) stopped safely below target at $physical physical hands"
    }
}
