$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$sourceRun = 'models\sourcev4_heroawr_slumbot_mimicv2_3p28m_20260726'
$sourceRecordPath = Join-Path $sourceRun 'experiment_record.json'
$deadline = (Get-Date).AddHours(4)
while (
    -not (Test-Path -LiteralPath $sourceRecordPath -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $sourceRecordPath -PathType Leaf)) {
    throw 'Timed out waiting for mimic-v2 3.28M endpoint'
}
$sourceRecord = Get-Content -LiteralPath $sourceRecordPath -Raw |
    ConvertFrom-Json
if ($sourceRecord.decision -ne 'RETAIN_AND_SCREEN') {
    exit 0
}

$source = (Resolve-Path -LiteralPath (Join-Path $sourceRun 'latest.pt')).Path
$sourceHands = [int64]$sourceRecord.candidate_total_hands
$inheritedHands = (
    [int64]$sourceRecord.inherited_lineage_training_hands +
    [int64]$sourceRecord.new_training_hands
)
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
        throw "Missing mimic-v2 scale input: $path"
    }
}

$runDir = 'models\sourcev4_heroawr_slumbot_mimicv2_scale10m_20260726'
$trainingResume = $source
if (Test-Path -LiteralPath $runDir) {
    $existingManifestPath = Join-Path $runDir 'run_manifest.json'
    $existingCheckpointPath = Join-Path $runDir 'latest.pt'
    if (
        -not (Test-Path -LiteralPath $existingManifestPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $existingCheckpointPath -PathType Leaf)
    ) {
        throw "Incomplete mimic-v2 scale recovery state: $runDir"
    }
    $existingManifest = Get-Content -LiteralPath $existingManifestPath -Raw |
        ConvertFrom-Json
    if (
        $existingManifest.status -ne 'initialized' -or
        [int64]$existingManifest.total_hands -ne $sourceHands
    ) {
        throw "Refusing non-initialized mimic-v2 scale recovery: $runDir"
    }
    $trainingResume = (Resolve-Path -LiteralPath $existingCheckpointPath).Path
}
$args = @(
    '-X', 'utf8', '-u',
    'scripts/alpha_holdem/train_v5.py',
    '--device', 'cuda',
    '--workers', '20',
    '--hands-per-iter', '32768',
    '--total-hands', '10262472',
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
    '--run-id', 'sourcev4_heroawr_slumbot_mimicv2_scale10m_20260726',
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260816',
    '--max-runtime-seconds', '21600',
    '--resume', $trainingResume,
    '--allow-resume',
    '--no-reset-optimizer'
)
& python @args
if ($LASTEXITCODE -ne 0) {
    throw 'Mimic-v2 10M continuation failed'
}

$manifest = Get-Content -LiteralPath (
    Join-Path $runDir 'run_manifest.json'
) -Raw | ConvertFrom-Json
$candidate = (Resolve-Path -LiteralPath (Join-Path $runDir 'latest.pt')).Path
$candidateHands = [int64]$manifest.total_hands
$newHands = $candidateHands - $sourceHands
[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'The improving mimic-v2 adapter learning curve continues to yield ' +
        'transferable gains between 3.54M and 10.26M total counter hands.'
    )
    material_change = (
        'Unchanged adapter-only critic-v2 GAE-0.95 PPO continuation with ' +
        'optimizer state preserved from the frozen 3.54M endpoint.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $source -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    new_training_hands = $newHands
    inherited_lineage_training_hands = $inheritedHands
    offline_decision_samples = 500000
    candidate_checkpoint = $candidate
    candidate_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $candidate -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    candidate_total_hands = $candidateHands
    run_fresh5k = $true
    decision = 'RETAIN_AND_SCREEN'
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $runDir 'experiment_record.json') `
        -Encoding UTF8

$externalDir = (
    'models\bench_sourcev4_heroawr_slumbot_mimicv2_' +
    'scale10m_pure_fresh5k_20260726'
)
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $candidate `
    -Tag 'sourcev4_heroawr_slumbot_mimicv2_scale10m_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Mimic-v2 scale10M fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_heroawr_slumbot_mimicv2_scale10m' `
    -QuickDir $externalDir `
    -SourcePolicy $candidate `
    -OutputStem 'sourcev4_heroawr_slumbot_mimicv2_scale10m' `
    -TrainingMethod `
    'optimizer-preserving 10M continuation of critic-v2 GAE-0.95 mimic-v2 adapter' `
    -NewTrainingHands $newHands `
    -InheritedLineageTrainingHands $inheritedHands `
    -OfflineDecisionSamples 500000
exit $LASTEXITCODE
