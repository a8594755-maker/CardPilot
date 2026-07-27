$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

# Keep at most two GPU optimizers alive.  The marker is written after the
# older all-in-EV trainer has released its GPU and before its CPU benchmark.
$slotMarker = (
    'models\sourcev4_fullnet_allstreet_mimic3_' +
    'aggressive_allinev10m_20260726\experiment_record.json'
)
$deadline = (Get-Date).AddHours(2)
while (
    -not (Test-Path -LiteralPath $slotMarker -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $slotMarker -PathType Leaf)) {
    throw 'Timed out waiting for the all-in-EV GPU slot'
}

$sourceDir = (
    'models\sourcev4_slumbot_history500k_allstreet_' +
    'imitation_fullnet_20260726'
)
$sourceRecord = Get-Content -LiteralPath (
    Join-Path $sourceDir 'experiment_record.json'
) -Raw | ConvertFrom-Json
$source = (Resolve-Path -LiteralPath $sourceRecord.candidate_checkpoint).Path
$sourceSha = (
    Get-FileHash -LiteralPath $source -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($sourceSha -ne [string]$sourceRecord.candidate_checkpoint_sha256) {
    throw 'All-in-EV imitation-anchor source hash mismatch'
}
$sourceHands = 262472

$fixedOpponents = @(
    (Resolve-Path -LiteralPath (Join-Path $sourceDir 'best.pt')).Path,
    (Resolve-Path -LiteralPath (Join-Path $sourceDir 'epoch_7.pt')).Path,
    (Resolve-Path -LiteralPath (Join-Path $sourceDir 'epoch_6.pt')).Path
)
$expectedOpponentShas = @(
    'dab38d18b7e57328734dffd18d50aa2c8042a284be8dc70dc939dd3bae5616f9',
    '160a1b48a5eadd5a74a12f2357ccd6fbbacf2dbef73bcd1a918ee8d361dc1376',
    'b14e8ee83b5821ef18da3e1f0f2917c8e8a2d99ec930a75d8818b53c306fe0c9'
)
for ($i = 0; $i -lt $fixedOpponents.Count; $i++) {
    $observed = (Get-FileHash -LiteralPath $fixedOpponents[$i] `
        -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($observed -ne $expectedOpponentShas[$i]) {
        throw "All-in-EV fixed-opponent hash mismatch: $($fixedOpponents[$i])"
    }
}

$runDir = (
    'models\sourcev4_imitation_anchor_' +
    'mixedselfplay_allinev10m_20260726'
)
if (Test-Path -LiteralPath $runDir) {
    throw "All-in-EV imitation-anchor output already exists: $runDir"
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
    '--source-policy-kl-coef', '5.0',
    '--separate-preflop-head',
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
    '--allin-runout-ev',
    '--allin-runout-ev-max-runouts', '200',
    '--snapshot-every', '100',
    '--save-interval', '10',
    '--archive-checkpoint-every', '100',
    '--run-id',
    'sourcev4_imitation_anchor_mixedselfplay_allinev10m_20260726',
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260828',
    '--max-runtime-seconds', '14400',
    '--resume', $source,
    '--allow-resume',
    '--reset-optimizer'
)
& python @args
if ($LASTEXITCODE -ne 0) {
    throw 'All-in-EV imitation-anchor mixed-self-play training failed'
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
        'The direct-imitation actor is the best credible anchor, while ' +
        'bounded all-in EV can reduce the dominant tail variance during its ' +
        'mixed-self-play correction.'
    )
    material_change = (
        'Paired with the non-EV imitation-anchor run: same source, seed, ' +
        'league, optimizer, KL and 40% self-play; enable only bounded-200 ' +
        'all-in runout EV rewards.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
    new_training_hands = $newHands
    inherited_lineage_training_hands = $sourceHands
    inherited_offline_decision_samples = 750000
    self_play_fraction = 0.4
    opponent_group_count = 5
    allin_runout_ev = $true
    allin_runout_ev_max_runouts = 200
    optimizer = 'fresh AdamW'
    critic_migration = 'critic_v1 actor exact copy; fresh normalized critic_v2'
    candidate_checkpoint = $candidate
    candidate_checkpoint_sha256 = (
        Get-FileHash -LiteralPath $candidate -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    candidate_total_hands = $candidateHands
    run_fresh5k = $true
    decision = 'READY_FOR_PURE_FRESH5K'
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
} | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath (Join-Path $runDir 'experiment_record.json') `
        -Encoding UTF8
exit 0
