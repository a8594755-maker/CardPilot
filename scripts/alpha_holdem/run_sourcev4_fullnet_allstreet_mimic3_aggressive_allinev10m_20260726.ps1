$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

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
$allstreetRecord = Get-Content -LiteralPath (
    Join-Path $allstreetDir 'experiment_record.json'
) -Raw | ConvertFrom-Json
if ($allstreetRecord.decision -ne 'RETAIN_AS_TRAINING_OPPONENT') {
    throw 'All-street opponent is not retained'
}
$fixedOpponents = @(
    $allstreetRecord.candidate_checkpoint,
    (Join-Path $allstreetDir 'epoch_7.pt'),
    (Join-Path $allstreetDir 'epoch_6.pt'),
    'models\sourcev4_slumbot_history500k_postflop_imitation_fullnet_20260726\best.pt',
    $source
)
foreach ($path in @($source) + $fixedOpponents) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing all-in-EV mimic-v3 input: $path"
    }
}

$runDir = (
    'models\sourcev4_fullnet_allstreet_mimic3_' +
    'aggressive_allinev10m_20260726'
)
if (Test-Path -LiteralPath $runDir) {
    throw "Aggressive all-in-EV mimic-v3 output already exists: $runDir"
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
    '--lr', '0.00001',
    '--preflop-head-lr', '0.000003',
    '--ppo-epochs', '3',
    '--ppo-target-kl', '0.01',
    '--source-policy-kl-coef', '0.5',
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
    '--allin-runout-ev',
    '--allin-runout-ev-max-runouts', '200',
    '--snapshot-every', '100',
    '--save-interval', '10',
    '--archive-checkpoint-every', '100',
    '--run-id',
    'sourcev4_fullnet_allstreet_mimic3_aggressive_allinev10m_20260726',
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260824',
    '--max-runtime-seconds', '14400',
    '--resume', $source,
    '--allow-resume',
    '--reset-optimizer'
)
& python @args
if ($LASTEXITCODE -ne 0) {
    throw 'Aggressive all-in-EV all-street mimic-v3 10M training failed'
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
        'The held-out-qualified all-street league can improve external play, ' +
        'but sampled all-in runouts give the actor a high-variance tail target.'
    )
    material_change = (
        'From the same source, league, optimizer reset and aggressive PPO ' +
        'configuration, replace only all-in-before-river terminal rewards ' +
        'with deterministic bounded-200-runout EV during training.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $source -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    new_training_hands = $newHands
    inherited_lineage_training_hands = $inheritedHands
    inherited_offline_decision_samples = 500000
    opponent_imitation_decision_samples = (
        [int64]$allstreetRecord.offline_decision_samples
    )
    optimizer = 'fresh AdamW'
    learning_rate = 0.00001
    preflop_head_learning_rate = 0.000003
    source_policy_kl_coef = 0.5
    allin_runout_ev = $true
    allin_runout_ev_max_runouts = 200
    deployment_policy = 'pure-network greedy-direct; no runtime override'
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
    'models\bench_sourcev4_fullnet_allstreet_mimic3_' +
    'aggressive_allinev10m_pure_fresh5k_20260726'
)
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $candidate `
    -Tag `
    'sourcev4_fullnet_allstreet_mimic3_aggressive_allinev10m_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Aggressive all-in-EV all-street mimic-v3 fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_fullnet_allstreet_mimic3_aggressive_allinev10m' `
    -QuickDir $externalDir `
    -SourcePolicy $candidate `
    -OutputStem 'sourcev4_fullnet_allstreet_mimic3_aggressive_allinev10m' `
    -TrainingMethod `
    'aggressive-full-network-PPO-allin-EV-against-qualified-mimic-v3' `
    -NewTrainingHands $newHands `
    -InheritedLineageTrainingHands $inheritedHands `
    -OfflineDecisionSamples 500000
exit $LASTEXITCODE
