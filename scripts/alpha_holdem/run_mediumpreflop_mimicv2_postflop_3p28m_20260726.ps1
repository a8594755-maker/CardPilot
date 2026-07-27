$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$source = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_heroawr_bbpreflop_awr_medium_20260726\' +
        'selected.pt'
    )
).Path
$mimicDir = (
    'models\sourcev4_slumbot_history500k_postflop_imitation_' +
    'fullnet_20260726'
)
$fixedOpponents = @(
    (Join-Path $mimicDir 'best.pt'),
    (Join-Path $mimicDir 'epoch_1.pt'),
    'models\sourcev4_slumbot_history500k_imitation_adapter256_kl01_mappingfix_20260726\best.pt',
    'models\sourcev4_slumbot_composed_preflopformal100k_e5_postflophistory500k_e4_20260726\latest.pt',
    $source
)
foreach ($path in @($source) + $fixedOpponents) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing medium-preflop mimic-v2 input: $path"
    }
}

$runDir = (
    'models\mediumpreflop_heroawr_slumbot_mimicv2_' +
    'postflop_3p28m_20260726'
)
if (Test-Path -LiteralPath $runDir) {
    throw "Medium-preflop mimic-v2 output already exists: $runDir"
}
$args = @(
    '-X', 'utf8', '-u',
    'scripts/alpha_holdem/train_v5.py',
    '--device', 'cuda',
    '--workers', '12',
    '--hands-per-iter', '32768',
    '--total-hands', '3540152',
    '--starting-stack', '200',
    '--env-version', 'v55preflopv2v4obs',
    '--norm-layer', 'gn',
    '--lr', '0.00003',
    '--ppo-epochs', '3',
    '--ppo-target-kl', '0.01',
    '--source-policy-kl-coef', '0.25',
    '--policy-postflop-only',
    '--separate-preflop-head',
    '--postflop-adapter-hidden', '256',
    '--adapter-only-training',
    '--critic-contract', 'critic_v2',
    '--h1-effective-stack-divisor', '200',
    '--value-coef', '1.0',
    '--autonomous-critic-v2-reset',
    '--mini-batch-size', '2048',
    '--epsilon', '0',
    '--gamma', '0.999',
    '--gae-lambda', '0.95',
    '--delta1', '3',
    '--entropy-coef', '0.002',
    '--entropy-floor', '0',
    '--k-best', '3',
    '--pool-strategy', 'latest',
    '--self-play-fraction', '0',
    '--opponent-assignment', 'per-group',
    '--opponent-groups', '5',
    '--fixed-opponent-checkpoints'
) + $fixedOpponents + @(
    '--rollout-mode', 'multi',
    '--rollout-envs-per-worker', '40',
    '--inference-min-batch-slots', '128',
    '--inference-batch-deadline-us', '1000',
    '--snapshot-every', '25',
    '--save-interval', '5',
    '--archive-checkpoint-every', '25',
    '--run-id',
    'mediumpreflop_heroawr_slumbot_mimicv2_postflop_3p28m_20260726',
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260815',
    '--max-runtime-seconds', '10800',
    '--resume', $source,
    '--allow-resume',
    '--reset-optimizer'
)
& python @args
if ($LASTEXITCODE -ne 0) {
    throw 'Medium-preflop mimic-v2 postflop training failed'
}

$manifest = Get-Content -LiteralPath (
    Join-Path $runDir 'run_manifest.json'
) -Raw | ConvertFrom-Json
$candidate = (Resolve-Path -LiteralPath (Join-Path $runDir 'latest.pt')).Path
$candidateHands = [int64]$manifest.total_hands
$newHands = $candidateHands - 262472
[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'Postflop PPO trained under the medium preflop policy reach ' +
        'distribution will transfer better than independently composing a ' +
        'postflop adapter trained under the source preflop policy.'
    )
    material_change = (
        'Freeze the retained medium AWR preflop head and train only the ' +
        'postflop adapter with critic-v2 GAE-0.95 against mimic-v2.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $source -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    fixed_opponents = @(
        foreach ($path in $fixedOpponents) {
            [ordered]@{
                path = (Resolve-Path -LiteralPath $path).Path
                sha256 = (
                    Get-FileHash -LiteralPath $path -Algorithm SHA256
                ).Hash.ToLowerInvariant()
            }
        }
    )
    new_training_hands = $newHands
    inherited_lineage_training_hands = 1446442
    offline_decision_samples = 600000
    opponent_imitation_decision_samples = 500000
    candidate_checkpoint = $candidate
    candidate_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $candidate -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    candidate_total_hands = $candidateHands
    run_fresh5k = $true
    decision = 'RETAIN_AND_SCREEN'
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath (Join-Path $runDir 'experiment_record.json') `
        -Encoding UTF8

$externalDir = (
    'models\bench_mediumpreflop_heroawr_slumbot_mimicv2_' +
    'postflop_3p28m_pure_fresh5k_20260726'
)
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $candidate `
    -Tag `
    'mediumpreflop_heroawr_slumbot_mimicv2_postflop_3p28m_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Medium-preflop mimic-v2 postflop fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'mediumpreflop_heroawr_slumbot_mimicv2_postflop_3p28m' `
    -QuickDir $externalDir `
    -SourcePolicy $candidate `
    -OutputStem 'mediumpreflop_heroawr_slumbot_mimicv2_postflop_3p28m' `
    -TrainingMethod `
    'medium preflop AWR plus reach-matched critic-v2 GAE-0.95 postflop PPO' `
    -NewTrainingHands $newHands `
    -InheritedLineageTrainingHands 1446442 `
    -OfflineDecisionSamples 600000
exit $LASTEXITCODE
