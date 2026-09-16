$ErrorActionPreference = 'Stop'

$experiment = 'research/experiments/v6-static-current-kl-4m-scale-20260904'
$parentExperiment = 'research/experiments/v6-static-current-kl-2m-scale-20260904'
$standard10 = 'models/baseline/standard10/latest.pt'
$standard10Sha = '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
$anchor2 = 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/slumbot_free_anchor_position10m.pt'
$anchor3 = 'C:/Users/a8594/CardPilot_legacy_20260829/selected_assets/opponents/corrected_cfr96_anchor10.pt'
$targetPhysicalHands = 4194304

$seed2Source = "$experiment/recovery_sources/seed2_guard1_iter768_hands3163932_physical3619473.pt"
$seed2SourceSha = '466b471fb404b89145e44a12e28c781ffc161f881f5b4cf4c5c3ba16fba9e77a'
$seed2AssignmentTailSha = 'ffec7162a8079863b2f4a50f3d79bc5c34d238196396d42098754e17b020fdd5'

$seeds = @(
    @{
        Name='seed2'; Seed=20263002; WorkerSeed=2026300200; DealStart=38300000
        RunId='v6_nashpg_static_seed2_20260903'; Resume=$seed2Source
        ResumeSha=$seed2SourceSha; ExistingOutput=$true
        ExpectedIteration=768; ExpectedHands=3163932
        ExpectedPhysical=3619473; ExpectedAssignmentIteration=769
        ExpectedAssignmentHands=3163932
        ExpectedAssignmentSha=$seed2AssignmentTailSha
        ExpectedMetricsFileSha='552ce125a09198305e1a8a9f8a411ecc56080f325f2adde99f1902aaa8d3bdae'
        ExpectedAssignmentFileSha='fa76a9be6a37a02cbdb5b496c4e8827fef6f9dad8ca4117dc2c02ffcb72312bf'
    },
    @{
        Name='seed3'; Seed=20263003; WorkerSeed=2026300300; DealStart=39300000
        RunId='v6_nashpg_static_seed3_20260903'
        Resume="$parentExperiment/seed3/latest.pt"
        ResumeSha='3e24831fc240e26bafe5389dd84b0f65d00f283de74f1580a2b86ae67ce6a7b0'
        ExistingOutput=$false; ExpectedIteration=440; ExpectedHands=1812162
        ExpectedPhysical=2099660; ExpectedAssignmentIteration=440
        ExpectedAssignmentHands=1808052
        ExpectedAssignmentSha='81d917af235505aee8042e9ab42a351be2f6b4d7cee1cd5de79a5f815d27aa1c'
        ExpectedMetricsFileSha='9392ae2831a449893f34060ca2ce8301c6f3375e8ec78b545143838f9092be33'
        ExpectedAssignmentFileSha='bd97ff2ff824553f66b55693dfd0d0156706b12188e10902eb96b51f82daad92'
    }
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

foreach ($seedInfo in $seeds) {
    $runDir = "$experiment/$($seedInfo.Name)"
    $out = "$runDir/latest.pt"
    $assignment = "$runDir/opponent_assignments.jsonl"
    $metrics = "$runDir/h1_training_metrics.jsonl"
    $resume = [string]$seedInfo.Resume

    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $resume).Hash.ToLower() -ne $seedInfo.ResumeSha) {
        throw "Recovery source SHA256 mismatch for $($seedInfo.Name)"
    }
    if ($seedInfo.ExistingOutput) {
        if ((Get-FileHash -Algorithm SHA256 -LiteralPath $out).Hash.ToLower() -ne $seedInfo.ResumeSha) {
            throw "Live output no longer matches frozen guard source for $($seedInfo.Name)"
        }
    } elseif (Test-Path -LiteralPath $out -PathType Leaf) {
        throw "Refusing to overwrite unexpected seed output: $out"
    }

    $checkpointSummary = & python -c "import json,torch; c=torch.load(r'$resume',map_location='cpu',weights_only=False); print(json.dumps({'iteration':int(c['iteration']),'hands':int(c['total_hands']),'physical':int(c['environment_hand_accounting']['completed_hands']),'lr':float(c['optimizer']['param_groups'][0]['lr']),'replay':len(c.get('ppo_replay_entries') or []),'replay_rng':c.get('ppo_replay_rng_state') is not None}))"
    if ($LASTEXITCODE -ne 0) { throw "Checkpoint inspection failed for $($seedInfo.Name)" }
    $checkpoint = $checkpointSummary | ConvertFrom-Json
    if (
        [int64]$checkpoint.iteration -ne [int64]$seedInfo.ExpectedIteration -or
        [int64]$checkpoint.hands -ne [int64]$seedInfo.ExpectedHands -or
        [int64]$checkpoint.physical -ne [int64]$seedInfo.ExpectedPhysical -or
        [math]::Abs([double]$checkpoint.lr - 0.0001) -gt 1e-12 -or
        [int64]$checkpoint.replay -ne 2 -or
        -not [bool]$checkpoint.replay_rng
    ) {
        throw "Checkpoint continuation contract mismatch for $($seedInfo.Name): $checkpointSummary"
    }

    $metricTail = Get-Content -LiteralPath $metrics -Tail 1 | ConvertFrom-Json
    $assignmentTail = Get-Content -LiteralPath $assignment -Tail 1 | ConvertFrom-Json
    if (
        (Get-FileHash -Algorithm SHA256 -LiteralPath $metrics).Hash.ToLower() -ne $seedInfo.ExpectedMetricsFileSha -or
        (Get-FileHash -Algorithm SHA256 -LiteralPath $assignment).Hash.ToLower() -ne $seedInfo.ExpectedAssignmentFileSha
    ) {
        throw "Metric/assignment evidence prefix SHA256 mismatch for $($seedInfo.Name)"
    }
    if (
        [int64]$metricTail.iteration -ne [int64]$seedInfo.ExpectedIteration -or
        [int64]$metricTail.hands -ne [int64]$seedInfo.ExpectedHands -or
        [int64]$assignmentTail.applies_to_iteration -ne [int64]$seedInfo.ExpectedAssignmentIteration -or
        [int64]$assignmentTail.total_hands_before_iteration -ne [int64]$seedInfo.ExpectedAssignmentHands -or
        [string]$assignmentTail.record_sha256 -ne [string]$seedInfo.ExpectedAssignmentSha
    ) {
        throw "Metric/assignment continuation boundary mismatch for $($seedInfo.Name)"
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
        '--run-id', [string]$seedInfo.RunId,
        '--run-dir', $runDir,
        '--out', $out,
        '--seed', [string]$seedInfo.Seed,
        '--max-runtime-seconds', '14400',
        '--resume', $resume,
        '--allow-resume',
        '--no-reset-optimizer',
        '--preserve-resumed-optimizer-lr',
        '--validate-stream'
    )
    Write-Host "Recovering static current-KL $($seedInfo.Name) from $resume"
    & python @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$($seedInfo.Name) recovery continuation failed with exit code $LASTEXITCODE"
    }
    $physical = [int64](& python -c "import torch; print(int(torch.load(r'$out',map_location='cpu',weights_only=False)['environment_hand_accounting']['completed_hands']))")
    if ($physical -lt $targetPhysicalHands) {
        throw "$($seedInfo.Name) stopped safely below target at $physical physical hands"
    }
}
