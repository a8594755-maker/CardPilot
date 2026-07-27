$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$sourceRecordPath = (
    'models\sourcev4_imitation_anchor_' +
    'specialist10m_from10m_20260726\experiment_record.json'
)
$deadline = [datetime]'2026-08-01T23:30:00'
while (
    -not (Test-Path -LiteralPath $sourceRecordPath -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $sourceRecordPath -PathType Leaf)) {
    throw 'Timed out waiting for the 10M specialist endpoint'
}

$sourceRecord = Get-Content -LiteralPath $sourceRecordPath -Raw |
    ConvertFrom-Json
$source = (Resolve-Path -LiteralPath $sourceRecord.candidate_checkpoint).Path
$sourceSha = (
    Get-FileHash -LiteralPath $source -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($sourceSha -ne [string]$sourceRecord.candidate_checkpoint_sha256) {
    throw 'Specialist-mixed source hash mismatch'
}
$sourceHands = [int64]$sourceRecord.candidate_total_hands

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

$runDir = (
    'models\sourcev4_imitation_anchor_' +
    'specialist_mixed40m_from20m_20260726'
)
if (Test-Path -LiteralPath $runDir) {
    throw "Specialist-mixed output already exists: $runDir"
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
    '--lr', '0.000001',
    '--preflop-head-lr', '0.00000035',
    '--ppo-epochs', '3',
    '--ppo-target-kl', '0.005',
    '--source-policy-kl-coef', '2.0',
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
    '--self-play-fraction', '0.25',
    '--opponent-assignment', 'per-group',
    '--opponent-groups', '4',
    '--fixed-opponent-checkpoints'
) + $fixedOpponents + @(
    '--rollout-mode', 'multi',
    '--rollout-envs-per-worker', '40',
    '--inference-min-batch-slots', '128',
    '--inference-batch-deadline-us', '1000',
    '--snapshot-every', '200',
    '--save-interval', '20',
    '--archive-checkpoint-every', '200',
    '--run-id',
    'sourcev4_imitation_anchor_specialist_mixed40m_from20m_20260726',
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260832',
    '--max-runtime-seconds', '57600',
    '--resume', $source,
    '--allow-resume',
    '--reset-optimizer'
)
& python @args
if ($LASTEXITCODE -ne 0) {
    throw 'Specialist-mixed 40M extension failed'
}

$manifest = Get-Content -LiteralPath (
    Join-Path $runDir 'run_manifest.json'
) -Raw | ConvertFrom-Json
$candidate = (Resolve-Path -LiteralPath (Join-Path $runDir 'latest.pt')).Path
$candidateHands = [int64]$manifest.total_hands
[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'After a 10M Slumbot-specialist phase, a longer low-rate continuation ' +
        'with one self-play group and three Slumbot-imitation groups should ' +
        'retain opponent-specific gains while improving general robustness.'
    )
    material_change = (
        'Continue the 20M-lineage specialist for 40M additional hands with a ' +
        'fresh optimizer, lr=1e-6, preflop lr=3.5e-7, KL=2, self-play=0.25, ' +
        'and three unchanged Slumbot-imitation opponents.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
    new_training_hands = $candidateHands - $sourceHands
    inherited_lineage_training_hands = $sourceHands
    inherited_offline_decision_samples = 750000
    self_play_fraction = 0.25
    opponent_group_count = 4
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
