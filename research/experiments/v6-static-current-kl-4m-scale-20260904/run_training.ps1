$ErrorActionPreference = 'Stop'

$experiment = 'research/experiments/v6-static-current-kl-4m-scale-20260904'
$parentExperiment = 'research/experiments/v6-static-current-kl-2m-scale-20260904'
$standard10 = 'models/baseline/standard10/latest.pt'
$standard10Sha = '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
$anchor2 = 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/slumbot_free_anchor_position10m.pt'
$anchor3 = 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/corrected_cfr96_anchor10.pt'
$targetPhysicalHands = 4194304

$seeds = @(
    @{ Name='seed1'; Seed=20263001; WorkerSeed=2026300100; DealStart=37300000; RunId='v6_nashpg_static_seed1_20260903'; CheckpointSha='fba34e5690efc7faa6747adb84d29ff576382711dfcfee885c4728a67248868f'; MetricsSha='d1e7bba710ba8f6548715bc0449d6389633a59bf6de318d717940d20f026fa7c'; AssignmentSha='c1b9b99366a8236fc3a22fd222a1cb7aaa4f4c9f5415b3913ecc3566c38feaa3' },
    @{ Name='seed2'; Seed=20263002; WorkerSeed=2026300200; DealStart=38300000; RunId='v6_nashpg_static_seed2_20260903'; CheckpointSha='82f21bf84eb8c7acf90ff64321e17d79f467f6fa5aa8adbbe6ddcf09bb4514fe'; MetricsSha='9d1cc118092bf25b4865f826fd2e2429f9ad6d31b17d9c020b56b0c778c7fbbe'; AssignmentSha='7ad9c7f826511cefccdd29c904e8f954f1040768cd36f32e18c67fe537c8f834' },
    @{ Name='seed3'; Seed=20263003; WorkerSeed=2026300300; DealStart=39300000; RunId='v6_nashpg_static_seed3_20260903'; CheckpointSha='3e24831fc240e26bafe5389dd84b0f65d00f283de74f1580a2b86ae67ce6a7b0'; MetricsSha='9392ae2831a449893f34060ca2ce8301c6f3375e8ec78b545143838f9092be33'; AssignmentSha='bd97ff2ff824553f66b55693dfd0d0156706b12188e10902eb96b51f82daad92' }
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
    --deal-start seed1=37300000 `
    --deal-start seed2=38300000 `
    --deal-start seed3=39300000 `
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
        '--max-runtime-seconds', '14400',
        '--resume', $parentCheckpoint,
        '--allow-resume',
        '--no-reset-optimizer',
        '--preserve-resumed-optimizer-lr',
        '--validate-stream'
    )
    Write-Host "Continuing static current-KL $($seedInfo.Name) to 4M"
    & python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$($seedInfo.Name) continuation failed with exit code $LASTEXITCODE"
    }
    $physical = [int64](& python -c "import torch; print(int(torch.load(r'$out',map_location='cpu',weights_only=False)['environment_hand_accounting']['completed_hands']))")
    if ($physical -lt $targetPhysicalHands) {
        throw "$($seedInfo.Name) stopped safely below target at $physical physical hands"
    }
}
