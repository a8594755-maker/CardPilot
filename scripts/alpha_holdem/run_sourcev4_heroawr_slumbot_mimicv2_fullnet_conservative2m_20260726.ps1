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
    throw 'Timed out waiting for the mimic-v2 adapter endpoint'
}
$sourceRecord = Get-Content -LiteralPath $sourceRecordPath -Raw |
    ConvertFrom-Json
if ($sourceRecord.decision -ne 'RETAIN_AND_SCREEN') {
    exit 0
}

$source = (Resolve-Path -LiteralPath (Join-Path $sourceRun 'latest.pt')).Path
$sourceHands = [int64]$sourceRecord.candidate_total_hands
$targetHands = $sourceHands + 2000000
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
        throw "Missing conservative full-network input: $path"
    }
}

$runDir = (
    'models\sourcev4_heroawr_slumbot_mimicv2_' +
    'fullnet_conservative2m_20260726'
)
$trainingResume = $source
if (Test-Path -LiteralPath $runDir) {
    $existingManifestPath = Join-Path $runDir 'run_manifest.json'
    $existingCheckpointPath = Join-Path $runDir 'latest.pt'
    if (
        -not (Test-Path -LiteralPath $existingManifestPath -PathType Leaf) -or
        -not (Test-Path -LiteralPath $existingCheckpointPath -PathType Leaf)
    ) {
        throw "Incomplete conservative full-network recovery state: $runDir"
    }
    $existingManifest = Get-Content -LiteralPath $existingManifestPath -Raw |
        ConvertFrom-Json
    if (
        $existingManifest.status -ne 'initialized' -or
        [int64]$existingManifest.total_hands -ne $sourceHands
    ) {
        throw "Refusing non-initialized full-network recovery: $runDir"
    }
    $trainingResume = (Resolve-Path -LiteralPath $existingCheckpointPath).Path
}

$args = @(
    '-X', 'utf8', '-u',
    'scripts/alpha_holdem/train_v5.py',
    '--device', 'cuda',
    '--workers', '12',
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
    '--snapshot-every', '25',
    '--save-interval', '5',
    '--archive-checkpoint-every', '25',
    '--run-id',
    'sourcev4_heroawr_slumbot_mimicv2_fullnet_conservative2m_20260726',
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260814',
    '--max-runtime-seconds', '10800',
    '--resume', $trainingResume,
    '--allow-resume',
    '--reset-optimizer'
)

& python @args
if ($LASTEXITCODE -ne 0) {
    throw 'Conservative full-network mimic-v2 training failed'
}

$candidate = Join-Path $runDir 'latest.pt'
$probeDir = Join-Path $runDir 'internal_endpoint'
New-Item -ItemType Directory -Path $probeDir | Out-Null
$genericJson = Join-Path $probeDir 'candidate.json'
& python -X utf8 -u `
    scripts/alpha_holdem/v5_internal_strength_probe.py `
    --checkpoint $candidate `
    --hands 1000 `
    --opponents aggressive call-station random `
    --max-pool-snapshots 0 `
    --device cuda `
    --starting-stack 200 `
    --seed 20260777 `
    --policy-mode greedy `
    --out-json $genericJson `
    --out-md (Join-Path $probeDir 'candidate.md')
if ($LASTEXITCODE -ne 0) {
    throw 'Conservative full-network generic probe failed'
}
$generic = Get-Content -LiteralPath $genericJson -Raw | ConvertFrom-Json

$mimicJson = Join-Path $probeDir 'candidate_mimic.json'
& python -X utf8 -u `
    scripts/alpha_holdem/v5_internal_strength_probe.py `
    --checkpoint $candidate `
    --hands 2000 `
    --checkpoint-opponent ($fixedOpponents[0]) `
    --checkpoint-opponent-only `
    --checkpoint-opponent-policy-mode sample `
    --max-pool-snapshots 0 `
    --device cuda `
    --starting-stack 200 `
    --seed 20260807 `
    --policy-mode greedy `
    --out-json $mimicJson `
    --out-md (Join-Path $probeDir 'candidate_mimic.md')
if ($LASTEXITCODE -ne 0) {
    throw 'Conservative full-network mimic-v2 probe failed'
}
$mimic = Get-Content -LiteralPath $mimicJson -Raw | ConvertFrom-Json

$candidateHands = [int64]$generic.checkpoint.total_hands
$newHands = $candidateHands - $sourceHands
[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'After the adapter learns the dominant postflop response, a tightly ' +
        'anchored full-network continuation can improve shared and preflop ' +
        'features without the KL instability of the direct full-network arm.'
    )
    material_change = (
        'Continue the retained mimic-v2 adapter endpoint for 2M hands with all ' +
        'actor weights trainable, shared lr=3e-6, preflop lr=1e-6, source KL=2.0.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $source -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    optimizer = 'PPO'
    learning_rate = 0.000003
    preflop_head_learning_rate = 0.000001
    source_policy_kl_coef = 2.0
    gae_lambda = 0.95
    trainable_scope = 'all_actor_weights_and_critic_v2'
    new_training_hands = $newHands
    inherited_lineage_training_hands = $inheritedHands
    offline_decision_samples = 500000
    candidate_checkpoint = (Resolve-Path -LiteralPath $candidate).Path
    candidate_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $candidate -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    candidate_total_hands = $candidateHands
    stable_internal_mean_bb_per_100 = [double](
        ($generic.results | Measure-Object -Property bb100 -Average).Average
    )
    mimic_v2_mean_bb_per_100 = [double](
        ($mimic.results | Measure-Object -Property bb100 -Average).Average
    )
    run_fresh5k = $true
    decision = 'RETAIN_AND_SCREEN'
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath (Join-Path $runDir 'experiment_record.json') `
        -Encoding UTF8

$externalDir = (
    'models\bench_sourcev4_heroawr_slumbot_mimicv2_' +
    'fullnet_conservative2m_pure_fresh5k_20260726'
)
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $candidate).Path `
    -Tag `
    'sourcev4_heroawr_slumbot_mimicv2_fullnet_conservative2m_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Conservative full-network mimic-v2 fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate `
    'sourcev4_heroawr_slumbot_mimicv2_fullnet_conservative2m' `
    -QuickDir $externalDir `
    -SourcePolicy $candidate `
    -OutputStem `
    'sourcev4_heroawr_slumbot_mimicv2_fullnet_conservative2m' `
    -TrainingMethod `
    'conservative all-street full-network continuation of mimic-v2 adapter' `
    -NewTrainingHands $newHands `
    -InheritedLineageTrainingHands $inheritedHands `
    -OfflineDecisionSamples 500000
exit $LASTEXITCODE
