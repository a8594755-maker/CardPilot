$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$allstreetRecordPath = (
    'models\sourcev4_slumbot_history500k_allstreet_' +
    'imitation_fullnet_20260726\experiment_record.json'
)
$bbSlotMarker = (
    'models\sourcev4_heroawr_mimicv2_' +
    'bbpostflop_3p28m_20260726\experiment_record.json'
)
$deadline = (Get-Date).AddHours(4)
while (
    (
        -not (Test-Path -LiteralPath $allstreetRecordPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $bbSlotMarker -PathType Leaf)
    ) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $allstreetRecordPath -PathType Leaf)) {
    throw 'Timed out waiting for the all-street opponent model'
}
if (-not (Test-Path -LiteralPath $bbSlotMarker -PathType Leaf)) {
    throw 'Timed out waiting for the BB-only GPU slot'
}

$allstreetRecord = Get-Content -LiteralPath $allstreetRecordPath -Raw |
    ConvertFrom-Json
if ($allstreetRecord.decision -ne 'RETAIN_AS_TRAINING_OPPONENT') {
    throw 'All-street opponent failed its held-out fidelity gate'
}
$sourceRun = (
    'models\sourcev4_heroawr_slumbot_mimicv2_' +
    'fullnet_conservative2m_20260726'
)
$sourceRecord = Get-Content -LiteralPath (
    Join-Path $sourceRun 'experiment_record.json'
) -Raw | ConvertFrom-Json
$source = (Resolve-Path -LiteralPath (Join-Path $sourceRun 'latest.pt')).Path
$sourceHands = [int64]$sourceRecord.candidate_total_hands
$inheritedHands = (
    [int64]$sourceRecord.inherited_lineage_training_hands +
    [int64]$sourceRecord.new_training_hands
)

$allstreetDir = (
    'models\sourcev4_slumbot_history500k_allstreet_' +
    'imitation_fullnet_20260726'
)
$fixedOpponents = @(
    $allstreetRecord.candidate_checkpoint,
    (Join-Path $allstreetDir 'epoch_7.pt'),
    (Join-Path $allstreetDir 'epoch_6.pt'),
    'models\sourcev4_slumbot_history500k_postflop_imitation_fullnet_20260726\best.pt',
    $source
)
foreach ($path in @($source) + $fixedOpponents) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing all-street mimic-v3 input: $path"
    }
}

$runDir = (
    'models\sourcev4_fullnet_allstreet_mimic3_' +
    'scale10m_20260726'
)
if (Test-Path -LiteralPath $runDir) {
    throw "All-street mimic-v3 output already exists: $runDir"
}
$targetHands = $sourceHands + 10000000
$args = @(
    '-X', 'utf8', '-u',
    'scripts/alpha_holdem/train_v5.py',
    '--device', 'cuda',
    '--workers', '20',
    '--hands-per-iter', '32768',
    '--total-hands', $targetHands,
    '--starting-stack', '200',
    '--env-version', 'v55preflopv2v4obs',
    '--norm-layer', 'gn',
    '--lr', '0.000003',
    '--preflop-head-lr', '0.000001',
    '--ppo-epochs', '3',
    '--ppo-target-kl', '0.005',
    '--source-policy-kl-coef', '2.0',
    '--separate-preflop-head',
    '--postflop-adapter-hidden', '256',
    '--critic-contract', 'critic_v2',
    '--h1-effective-stack-divisor', '200',
    '--value-coef', '1.0',
    '--autonomous-critic-v2-reset',
    '--mini-batch-size', '2048',
    '--epsilon', '0',
    '--gamma', '0.999',
    '--gae-lambda', '0.95',
    '--delta1', '3',
    '--entropy-coef', '0.001',
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
    '--snapshot-every', '100',
    '--save-interval', '10',
    '--archive-checkpoint-every', '100',
    '--run-id', 'sourcev4_fullnet_allstreet_mimic3_scale10m_20260726',
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260820',
    '--max-runtime-seconds', '14400',
    '--resume', $source,
    '--allow-resume',
    '--no-reset-optimizer'
)
& python @args
if ($LASTEXITCODE -ne 0) {
    throw 'All-street mimic-v3 10M continuation failed'
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
        'Replacing most of the old mimic-v2 league with the held-out-qualified ' +
        'all-street Slumbot model will reduce opponent-model exploitation and ' +
        'make full-network PPO gains transfer to fresh Slumbot hands.'
    )
    material_change = (
        'Continue the conservative full-network policy for 10M environment ' +
        'hands against a league with three all-street imitation checkpoints, ' +
        'one postflop specialist and the source policy.'
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
    inherited_lineage_training_hands = $inheritedHands
    inherited_offline_decision_samples = 500000
    opponent_imitation_decision_samples = (
        [int64]$allstreetRecord.offline_decision_samples
    )
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
    'models\bench_sourcev4_fullnet_allstreet_mimic3_' +
    'scale10m_pure_fresh5k_20260726'
)
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $candidate `
    -Tag 'sourcev4_fullnet_allstreet_mimic3_scale10m_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'All-street mimic-v3 10M fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_fullnet_allstreet_mimic3_scale10m' `
    -QuickDir $externalDir `
    -SourcePolicy $candidate `
    -OutputStem 'sourcev4_fullnet_allstreet_mimic3_scale10m' `
    -TrainingMethod `
    '10M conservative full-network PPO against held-out-qualified mimic-v3 league' `
    -NewTrainingHands $newHands `
    -InheritedLineageTrainingHands $inheritedHands `
    -OfflineDecisionSamples 500000
exit $LASTEXITCODE
