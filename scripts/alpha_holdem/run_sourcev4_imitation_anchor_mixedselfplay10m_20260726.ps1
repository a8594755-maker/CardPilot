$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

# A GPU slot was released after the externally rejected mixed continuation was
# stopped at its preserved partial checkpoint.

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
    throw 'Imitation-anchor source hash mismatch'
}
$sourceHands = 262472
$heroScreen = (
    'models\bench_sourcev4_slumbot_allstreet_imitation_' +
    'fullnet_hero_pure_fresh5k_20260726\promotion_decision.json'
)
$heroDecision = Get-Content -LiteralPath $heroScreen -Raw | ConvertFrom-Json
if ([int]$heroDecision.quick5k_hands -ne 5000) {
    throw 'Imitation-anchor source lacks a complete hero fresh5k'
}

$fixedOpponents = @(
    (Resolve-Path -LiteralPath (
        Join-Path $sourceDir 'best.pt'
    )).Path,
    (Resolve-Path -LiteralPath (
        Join-Path $sourceDir 'epoch_7.pt'
    )).Path,
    (Resolve-Path -LiteralPath (
        Join-Path $sourceDir 'epoch_6.pt'
    )).Path
)
if ($fixedOpponents.Count -ne 3) {
    throw "Expected three actor-compatible fixed opponents, got $($fixedOpponents.Count)"
}
$expectedOpponentShas = @(
    'dab38d18b7e57328734dffd18d50aa2c8042a284be8dc70dc939dd3bae5616f9',
    '160a1b48a5eadd5a74a12f2357ccd6fbbacf2dbef73bcd1a918ee8d361dc1376',
    'b14e8ee83b5821ef18da3e1f0f2917c8e8a2d99ec930a75d8818b53c306fe0c9'
)
for ($i = 0; $i -lt $fixedOpponents.Count; $i++) {
    $observed = (Get-FileHash -LiteralPath $fixedOpponents[$i] `
        -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($observed -ne $expectedOpponentShas[$i]) {
        throw "Fixed-opponent hash mismatch: $($fixedOpponents[$i])"
    }
}

$runDir = 'models\sourcev4_imitation_anchor_mixedselfplay10m_20260726'
if (Test-Path -LiteralPath $runDir) {
    throw "Imitation-anchor output already exists: $runDir"
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
    '--snapshot-every', '100',
    '--save-interval', '10',
    '--archive-checkpoint-every', '100',
    '--run-id', 'sourcev4_imitation_anchor_mixedselfplay10m_20260726',
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
    throw 'Imitation-anchor mixed-self-play 10M training failed'
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
        'The complete -21.5968 bb/100 imitation actor is a better anchor than ' +
        'the externally rejected imitation-only PPO endpoint. Strong source ' +
        'KL plus self-play should improve value learning without erasing its ' +
        'demonstrated behavior.'
    )
    material_change = (
        'Migrate the full-network imitation actor from critic_v1 to a fresh ' +
        'critic_v2, reset optimizer, and train 10M hands with KL=5 against ' +
        'two self-play groups and three fixed-opponent groups.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
    source_fresh5k_bb_per_100 = [double]$heroDecision.quick5k_bb_per_100
    source_fresh5k_ci95_lower = [double]$heroDecision.quick5k_ci95_lower
    source_fresh5k_ci95_upper = [double]$heroDecision.quick5k_ci95_upper
    new_training_hands = $newHands
    inherited_lineage_training_hands = $sourceHands
    inherited_offline_decision_samples = 750000
    self_play_fraction = 0.4
    opponent_group_count = 5
    fixed_opponents = @(
        for ($i = 0; $i -lt $fixedOpponents.Count; $i++) {
            [ordered]@{
                path = $fixedOpponents[$i]
                sha256 = $expectedOpponentShas[$i]
            }
        }
    )
    optimizer = 'fresh AdamW'
    critic_migration = 'critic_v1 actor exact copy; fresh normalized critic_v2'
    learning_rate = 0.000003
    preflop_head_learning_rate = 0.000001
    source_policy_kl_coef = 5.0
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
    'models\bench_sourcev4_imitation_anchor_' +
    'mixedselfplay10m_pure_fresh5k_20260726'
)
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $candidate `
    -Tag 'sourcev4_imitation_anchor_mixedselfplay10m_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Imitation-anchor mixed-self-play fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_imitation_anchor_mixedselfplay10m' `
    -QuickDir $externalDir `
    -SourcePolicy $candidate `
    -OutputStem 'sourcev4_imitation_anchor_mixedselfplay10m' `
    -TrainingMethod 'imitation-anchor-strong-KL-mixed-self-play-PPO' `
    -NewTrainingHands $newHands `
    -InheritedLineageTrainingHands $sourceHands `
    -OfflineDecisionSamples 750000
exit $LASTEXITCODE
