$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$sourceRun = 'models\sourcev4_heroawr_slumbot_mimicv2_scale10m_20260726'
$sourceRecordPath = Join-Path $sourceRun 'experiment_record.json'
if (-not (Test-Path -LiteralPath $sourceRecordPath -PathType Leaf)) {
    throw 'Missing completed 10M mimic-v2 source record'
}
$sourceRecord = Get-Content -LiteralPath $sourceRecordPath -Raw |
    ConvertFrom-Json
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
    'models\sourcev4_heroawr_slumbot_mimicv2_3p28m_20260726\latest.pt'
)
foreach ($path in @($source) + $fixedOpponents) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing mimic-v2 scale50M input: $path"
    }
}

$runDir = 'models\sourcev4_heroawr_slumbot_mimicv2_scale50m_20260726'
if (Test-Path -LiteralPath $runDir) {
    throw "Mimic-v2 scale50M output already exists: $runDir"
}
$targetHands = $sourceHands + 40000000
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
    '--snapshot-every', '500',
    '--save-interval', '10',
    '--archive-checkpoint-every', '500',
    '--run-id', 'sourcev4_heroawr_slumbot_mimicv2_scale50m_20260726',
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260821',
    '--max-runtime-seconds', '21600',
    '--resume', $source,
    '--allow-resume',
    '--no-reset-optimizer'
)
& python @args
if ($LASTEXITCODE -ne 0) {
    throw 'Mimic-v2 50M continuation failed'
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
        'The external improvement emerging at the 10.28M endpoint continues ' +
        'along the unchanged adapter-only mimic-v2 learning curve toward the ' +
        'next 50M-scale environment-hand milestone.'
    )
    material_change = (
        'Preserve optimizer, architecture, league, critic-v2 GAE-0.95, and ' +
        'postflop adapter-only scope while adding 40M environment hands.'
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
    'scale50m_pure_fresh5k_20260726'
)
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $candidate `
    -Tag 'sourcev4_heroawr_slumbot_mimicv2_scale50m_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Mimic-v2 scale50M fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_heroawr_slumbot_mimicv2_scale50m' `
    -QuickDir $externalDir `
    -SourcePolicy $candidate `
    -OutputStem 'sourcev4_heroawr_slumbot_mimicv2_scale50m' `
    -TrainingMethod `
    'optimizer-preserving 50M-scale mimic-v2 adapter-only PPO continuation' `
    -NewTrainingHands $newHands `
    -InheritedLineageTrainingHands $inheritedHands `
    -OfflineDecisionSamples 500000
exit $LASTEXITCODE
