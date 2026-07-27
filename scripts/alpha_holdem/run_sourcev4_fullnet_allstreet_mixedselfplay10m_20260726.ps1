$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$sourceRun = 'models\sourcev4_fullnet_allstreet_mimic3_scale10m_20260726'
$sourceRecord = Get-Content -LiteralPath (
    Join-Path $sourceRun 'experiment_record.json'
) -Raw | ConvertFrom-Json
$source = (Resolve-Path -LiteralPath $sourceRecord.candidate_checkpoint).Path
$sourceSha = (
    Get-FileHash -LiteralPath $source -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($sourceSha -ne [string]$sourceRecord.candidate_checkpoint_sha256) {
    throw 'Mixed-self-play source hash mismatch'
}
$sourceHands = [int64]$sourceRecord.candidate_total_hands
$inheritedHands = (
    [int64]$sourceRecord.inherited_lineage_training_hands +
    [int64]$sourceRecord.new_training_hands
)

$fixedOpponents = @(
    $sourceRecord.fixed_opponents | ForEach-Object { [string]$_.path }
)
if ($fixedOpponents.Count -ne 5) {
    throw "Expected five retained fixed opponents, got $($fixedOpponents.Count)"
}
foreach ($entry in $sourceRecord.fixed_opponents) {
    $path = (Resolve-Path -LiteralPath ([string]$entry.path)).Path
    $observed = (
        Get-FileHash -LiteralPath $path -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    if ($observed -ne [string]$entry.sha256) {
        throw "Fixed-opponent hash mismatch: $path"
    }
}

$runDir = 'models\sourcev4_fullnet_allstreet_mixedselfplay10m_20260726'
if (Test-Path -LiteralPath $runDir) {
    throw "Mixed-self-play output already exists: $runDir"
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
    '--self-play-fraction', '0.4',
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
    '--run-id', 'sourcev4_fullnet_allstreet_mixedselfplay10m_20260726',
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260826',
    '--max-runtime-seconds', '14400',
    '--resume', $source,
    '--allow-resume',
    '--no-reset-optimizer'
)
& python @args
if ($LASTEXITCODE -ne 0) {
    throw 'Mixed-self-play all-street 10M training failed'
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
        'Pure best-response training overfits residual errors in the Slumbot ' +
        'imitation league; mixing current-policy self-play should preserve ' +
        'general poker stability while retaining opponent-specific pressure.'
    )
    material_change = (
        'Continue the exact conservative endpoint for 10M hands with the same ' +
        'optimizer, learning rates, KL, architecture and five fixed opponents, ' +
        'but assign two of five worker groups to current-policy self-play.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
    new_training_hands = $newHands
    inherited_lineage_training_hands = $inheritedHands
    inherited_offline_decision_samples = 1250000
    self_play_fraction = 0.4
    opponent_group_count = 5
    fixed_opponent_count = $fixedOpponents.Count
    optimizer = 'continued AdamW'
    learning_rate = 0.000003
    preflop_head_learning_rate = 0.000001
    source_policy_kl_coef = 2.0
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
    'models\bench_sourcev4_fullnet_allstreet_' +
    'mixedselfplay10m_pure_fresh5k_20260726'
)
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $candidate `
    -Tag 'sourcev4_fullnet_allstreet_mixedselfplay10m_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Mixed-self-play all-street fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_fullnet_allstreet_mixedselfplay10m' `
    -QuickDir $externalDir `
    -SourcePolicy $candidate `
    -OutputStem 'sourcev4_fullnet_allstreet_mixedselfplay10m' `
    -TrainingMethod 'conservative-full-network-PPO-mimic-v3-plus-self-play' `
    -NewTrainingHands $newHands `
    -InheritedLineageTrainingHands $inheritedHands `
    -OfflineDecisionSamples 1250000
exit $LASTEXITCODE
