[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('standard', 'specialist-mixed')]
    [string]$Lineage
)

$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$rootRecordPath = (
    'models\sourcev4_imitation_anchor_' +
    'mixedselfplay10m_20260726\experiment_record.json'
)
$rootRecord = Get-Content -LiteralPath $rootRecordPath -Raw |
    ConvertFrom-Json
$fixedOpponents = @(
    $rootRecord.fixed_opponents | ForEach-Object {
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
    if ($observed -ne [string]$rootRecord.fixed_opponents[$i].sha256) {
        throw "Fixed-opponent hash mismatch: $($fixedOpponents[$i])"
    }
}

if ($Lineage -eq 'standard') {
    $sourceRun = (
        'models\sourcev4_imitation_anchor_' +
        'mixedselfplay50m_from10m_20260726'
    )
    $runId = (
        'sourcev4_imitation_anchor_' +
        'mixedselfplay250m_from60m_20260727'
    )
    $learningRate = '0.000001'
    $preflopLearningRate = '0.00000035'
    $sourceKl = '5.0'
    $selfPlayFraction = '0.4'
    $opponentGroups = '5'
    $seed = '20260840'
    $hypothesis = (
        'The strongest robust imitation-anchored lineage needs substantially ' +
        'more than 60M environment hands; a lower-rate 190M continuation ' +
        'should improve play while a strong source-policy KL limits drift.'
    )
    $materialChange = (
        'Continue the 60M standard mixed-self-play endpoint for about 190M ' +
        'additional hands with a fresh optimizer, lr=1e-6, preflop lr=3.5e-7, ' +
        'KL=5 and the unchanged 40% self-play/five-group league.'
    )
    $screenStem = 'sourcev4_imitation_anchor_mixedselfplay50m_from10m'
} else {
    $sourceRun = (
        'models\sourcev4_imitation_anchor_' +
        'specialist_mixed40m_from20m_20260726'
    )
    $runId = (
        'sourcev4_imitation_anchor_' +
        'specialist_mixed250m_from60m_20260727'
    )
    $learningRate = '0.0000007'
    $preflopLearningRate = '0.000000245'
    $sourceKl = '2.0'
    $selfPlayFraction = '0.25'
    $opponentGroups = '4'
    $seed = '20260841'
    $hypothesis = (
        'The Slumbot-specialist then mixed-self-play lineage has a stronger ' +
        'training signal but needs paper-direction scale to convert it into ' +
        'robust external play.'
    )
    $materialChange = (
        'Continue the 60M specialist-mixed endpoint for about 190M additional ' +
        'hands with a fresh optimizer, lr=7e-7, preflop lr=2.45e-7, KL=2 and ' +
        'the unchanged 25% self-play/four-group league.'
    )
    $screenStem = 'sourcev4_imitation_anchor_specialist_mixed40m_from20m'
}

$sourceRecordPath = Join-Path $sourceRun 'experiment_record.json'
$deadline = [datetime]'2026-08-01T23:30:00'
while (
    -not (Test-Path -LiteralPath $sourceRecordPath -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $sourceRecordPath -PathType Leaf)) {
    throw "Timed out waiting for $sourceRecordPath"
}

$sourceRecord = Get-Content -LiteralPath $sourceRecordPath -Raw |
    ConvertFrom-Json
$source = (Resolve-Path -LiteralPath $sourceRecord.candidate_checkpoint).Path
$sourceSha = (
    Get-FileHash -LiteralPath $source -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($sourceSha -ne [string]$sourceRecord.candidate_checkpoint_sha256) {
    throw "$Lineage 60M source hash mismatch"
}

# Do not spend several days extending a 60M endpoint that fresh Slumbot has
# already ruled out directionally.  A negative point estimate may continue
# when its interval still crosses zero, but a wholly negative interval or a
# worse-than -30 bb/100 point estimate stops this long continuation.
$quickDir = Join-Path (
    'models'
) "bench_${screenStem}_pure_fresh5k_20260726"
$quickDecisionPath = Join-Path $quickDir 'promotion_decision.json'
while (
    -not (Test-Path -LiteralPath $quickDecisionPath -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $quickDecisionPath -PathType Leaf)) {
    throw "Timed out waiting for $quickDecisionPath"
}
$quickDecision = Get-Content -LiteralPath $quickDecisionPath -Raw |
    ConvertFrom-Json
$quickBbPer100 = [double]$quickDecision.quick5k_bb_per_100
$quickUpper = [double]$quickDecision.quick5k_ci95_upper
if ($quickUpper -le 0 -or $quickBbPer100 -lt -30) {
    Write-Output (
        "$Lineage 250M continuation rejected by its completed 60M fresh5k: " +
        "bb/100=$quickBbPer100, CI95 upper=$quickUpper."
    )
    exit 0
}

$sourceHands = [int64]$sourceRecord.candidate_total_hands
$targetHands = 250000000 + ($sourceHands % 1000000)

$runDir = Join-Path 'models' $runId
if (Test-Path -LiteralPath $runDir) {
    throw "250M continuation output already exists: $runDir"
}

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
    '--lr', $learningRate,
    '--preflop-head-lr', $preflopLearningRate,
    '--ppo-epochs', '3',
    '--ppo-target-kl', '0.005',
    '--source-policy-kl-coef', $sourceKl,
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
    '--self-play-fraction', $selfPlayFraction,
    '--opponent-assignment', 'per-group',
    '--opponent-groups', $opponentGroups,
    '--fixed-opponent-checkpoints'
) + $fixedOpponents + @(
    '--rollout-mode', 'multi',
    '--rollout-envs-per-worker', '40',
    '--inference-min-batch-slots', '128',
    '--inference-batch-deadline-us', '1000',
    '--snapshot-every', '500',
    '--save-interval', '50',
    '--archive-checkpoint-every', '1000',
    '--run-id', $runId,
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', $seed,
    '--max-runtime-seconds', '100800',
    '--resume', $source,
    '--allow-resume',
    '--reset-optimizer'
)
& python @args
if ($LASTEXITCODE -ne 0) {
    throw "$Lineage 250M continuation failed"
}

$manifest = Get-Content -LiteralPath (
    Join-Path $runDir 'run_manifest.json'
) -Raw | ConvertFrom-Json
$candidate = (Resolve-Path -LiteralPath (Join-Path $runDir 'latest.pt')).Path
$candidateHands = [int64]$manifest.total_hands
[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = $hypothesis
    material_change = $materialChange
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
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
