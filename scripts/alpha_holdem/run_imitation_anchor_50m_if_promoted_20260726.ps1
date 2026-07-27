$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$quickDecisionPath = (
    'models\bench_sourcev4_imitation_anchor_' +
    'mixedselfplay10m_pure_fresh5k_20260726\promotion_decision.json'
)
$evRecordPath = (
    'models\sourcev4_imitation_anchor_' +
    'mixedselfplay_allinev10m_20260726\experiment_record.json'
)
$deadline = (Get-Date).AddHours(18)
foreach ($path in @($quickDecisionPath, $evRecordPath)) {
    while (
        -not (Test-Path -LiteralPath $path -PathType Leaf) -and
        (Get-Date) -lt $deadline
    ) {
        Start-Sleep -Seconds 20
    }
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Timed out waiting for $path"
    }
}

$quickDecision = Get-Content -LiteralPath $quickDecisionPath -Raw |
    ConvertFrom-Json
if (-not [bool]$quickDecision.promote_to_fresh20k) {
    Write-Output 'Standard 10M endpoint did not promote; 50M extension skipped.'
    exit 0
}

$sourceRun = 'models\sourcev4_imitation_anchor_mixedselfplay10m_20260726'
$sourceRecord = Get-Content -LiteralPath (
    Join-Path $sourceRun 'experiment_record.json'
) -Raw | ConvertFrom-Json
$source = (Resolve-Path -LiteralPath $sourceRecord.candidate_checkpoint).Path
$sourceSha = (
    Get-FileHash -LiteralPath $source -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($sourceSha -ne [string]$sourceRecord.candidate_checkpoint_sha256) {
    throw 'Standard 10M source hash mismatch'
}
$sourceHands = [int64]$sourceRecord.candidate_total_hands

$fixedOpponents = @(
    $sourceRecord.fixed_opponents | ForEach-Object {
        (Resolve-Path -LiteralPath ([string]$_.path)).Path
    }
)
if ($fixedOpponents.Count -ne 3) {
    throw "Expected three fixed opponents, got $($fixedOpponents.Count)"
}
for ($i = 0; $i -lt $fixedOpponents.Count; $i++) {
    $observed = (
        Get-FileHash -LiteralPath $fixedOpponents[$i] -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    if ($observed -ne [string]$sourceRecord.fixed_opponents[$i].sha256) {
        throw "Fixed-opponent hash mismatch: $($fixedOpponents[$i])"
    }
}

$runDir = (
    'models\sourcev4_imitation_anchor_' +
    'mixedselfplay50m_from10m_20260726'
)
if (Test-Path -LiteralPath $runDir) {
    throw "50M extension output already exists: $runDir"
}
$targetHands = $sourceHands + 50000000
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
    '--lr', '0.000002',
    '--preflop-head-lr', '0.0000007',
    '--ppo-epochs', '3',
    '--ppo-target-kl', '0.005',
    '--source-policy-kl-coef', '5.0',
    '--separate-preflop-head',
    '--critic-contract', 'critic_v2',
    '--autonomous-critic-v2-continue',
    '--h1-effective-stack-divisor', '200',
    '--value-coef', '1.0',
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
    '--snapshot-every', '200',
    '--save-interval', '20',
    '--archive-checkpoint-every', '200',
    '--run-id', 'sourcev4_imitation_anchor_mixedselfplay50m_from10m_20260726',
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260830',
    '--max-runtime-seconds', '64800',
    '--resume', $source,
    '--allow-resume',
    '--reset-optimizer'
)
& python @args
if ($LASTEXITCODE -ne 0) {
    throw 'Promoted imitation-anchor 50M extension failed'
}

$manifest = Get-Content -LiteralPath (
    Join-Path $runDir 'run_manifest.json'
) -Raw | ConvertFrom-Json
$candidate = (Resolve-Path -LiteralPath (Join-Path $runDir 'latest.pt')).Path
$candidateHands = [int64]$manifest.total_hands
[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'A 10M imitation-anchored mixed-self-play endpoint that passes the ' +
        'external fresh5k promotion screen should continue improving under a ' +
        'lower learning rate without losing its demonstrated policy.'
    )
    material_change = (
        'Continue the exact promoted 10M actor for 50M additional environment ' +
        'hands with a fresh optimizer, lr=2e-6, preflop lr=7e-7 and unchanged ' +
        'KL=5, league, observations, action abstraction and greedy-direct contract.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
    source_fresh5k_bb_per_100 = [double]$quickDecision.quick5k_bb_per_100
    source_fresh5k_ci95_lower = [double]$quickDecision.quick5k_ci95_lower
    source_fresh5k_ci95_upper = [double]$quickDecision.quick5k_ci95_upper
    new_training_hands = $candidateHands - $sourceHands
    inherited_lineage_training_hands = $sourceHands
    inherited_offline_decision_samples = 750000
    candidate_checkpoint = $candidate
    candidate_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $candidate -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    candidate_total_hands = $candidateHands
    decision = 'READY_FOR_PURE_FRESH5K'
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $runDir 'experiment_record.json') `
        -Encoding UTF8
exit 0
