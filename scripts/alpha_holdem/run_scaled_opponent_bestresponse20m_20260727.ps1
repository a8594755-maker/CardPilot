$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$scaledRecordPath = (
    'models\sourcev4_slumbot_history_allstreet_' +
    'imitation_scale1p25m_20260727\experiment_record.json'
)
$scaledRecord = Get-Content -LiteralPath $scaledRecordPath -Raw |
    ConvertFrom-Json
if ([string]$scaledRecord.decision -ne 'READY_FOR_PURE_FRESH5K') {
    throw 'Scaled opponent model failed its held-out fidelity gate'
}
$scaledOpponent = (
    Resolve-Path -LiteralPath $scaledRecord.candidate_checkpoint
).Path
$scaledSha = (
    Get-FileHash -LiteralPath $scaledOpponent -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($scaledSha -ne [string]$scaledRecord.candidate_checkpoint_sha256) {
    throw 'Scaled opponent checkpoint hash mismatch'
}

$sourceRecordPath = (
    'models\sourcev4_imitation_anchor_' +
    'mixedselfplay10m_20260726\experiment_record.json'
)
$sourceRecord = Get-Content -LiteralPath $sourceRecordPath -Raw |
    ConvertFrom-Json
$source = (Resolve-Path -LiteralPath $sourceRecord.candidate_checkpoint).Path
$sourceSha = (
    Get-FileHash -LiteralPath $source -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($sourceSha -ne [string]$sourceRecord.candidate_checkpoint_sha256) {
    throw 'Best-response source checkpoint hash mismatch'
}
$sourceHands = [int64]$sourceRecord.candidate_total_hands

$originalRecordPath = (
    'models\sourcev4_slumbot_history500k_allstreet_' +
    'imitation_fullnet_20260726\experiment_record.json'
)
$originalRecord = Get-Content -LiteralPath $originalRecordPath -Raw |
    ConvertFrom-Json
$originalOpponent = (
    Resolve-Path -LiteralPath $originalRecord.candidate_checkpoint
).Path
$originalSha = (
    Get-FileHash -LiteralPath $originalOpponent -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($originalSha -ne [string]$originalRecord.candidate_checkpoint_sha256) {
    throw 'Original opponent checkpoint hash mismatch'
}

$bbRecordPath = (
    'models\sourcev4_slumbot_history500k_allstreet_' +
    'imitation_fullnet_bbweight3_20260726\experiment_record.json'
)
$bbRecord = Get-Content -LiteralPath $bbRecordPath -Raw | ConvertFrom-Json
$bbOpponent = (Resolve-Path -LiteralPath $bbRecord.selected_checkpoint).Path
$bbSha = (
    Get-FileHash -LiteralPath $bbOpponent -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($bbSha -ne [string]$bbRecord.selected_checkpoint_sha256) {
    throw 'BB-weighted opponent checkpoint hash mismatch'
}

$fixedOpponents = @(
    $scaledOpponent,
    $bbOpponent,
    $originalOpponent
)
$runDir = (
    'models\sourcev4_standard10_scaledopponent_' +
    'bestresponse20m_20260727'
)
if (Test-Path -LiteralPath $runDir) {
    throw "Best-response output already exists: $runDir"
}
$targetHands = $sourceHands + 20000000
$trainArgs = @(
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
    '--preflop-head-lr', '0.0000003',
    '--ppo-epochs', '3',
    '--ppo-target-kl', '0.004',
    '--source-policy-kl-coef', '8.0',
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
    '--snapshot-every', '100',
    '--save-interval', '20',
    '--archive-checkpoint-every', '100',
    '--run-id', 'sourcev4_standard10_scaledopponent_bestresponse20m_20260727',
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260860',
    '--max-runtime-seconds', '21600',
    '--resume', $source,
    '--allow-resume',
    '--reset-optimizer'
)
& python @trainArgs
if ($LASTEXITCODE -ne 0) {
    throw 'Scaled-opponent best-response training failed'
}

$manifest = Get-Content -LiteralPath (
    Join-Path $runDir 'run_manifest.json'
) -Raw | ConvertFrom-Json
$candidate = (Resolve-Path -LiteralPath (Join-Path $runDir 'latest.pt')).Path
$candidateHands = [int64]$manifest.total_hands
[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'The standard10 policy is the strongest completed pure lineage, but ' +
        'its league used a 75.8%-accuracy Slumbot proxy. A higher-fidelity ' +
        '1.25M-row proxy plus BB-weighted and original diversity should give ' +
        'a more useful best-response gradient while KL=8 preserves the source.'
    )
    material_change = (
        'Start from exact standard10, reset the optimizer, and train 20M ' +
        'environment hands with one self-play group and three fixed Slumbot ' +
        'proxy groups; use lr=1e-6, preflop lr=3e-7 and source KL=8.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
    source_completed_fresh20k_bb_per_100 = -11.4275
    source_completed_fresh20k_ci95_lower = -28.7124362921855
    source_completed_fresh20k_ci95_upper = 5.85743629218548
    new_training_hands = $candidateHands - $sourceHands
    inherited_lineage_training_hands = $sourceHands
    inherited_offline_decision_samples = (
        [int64]$sourceRecord.inherited_offline_decision_samples
    )
    opponent_model_offline_decision_samples = (
        [int64]$scaledRecord.offline_decision_samples
    )
    self_play_fraction = 0.25
    opponent_group_count = 4
    fixed_opponents = @(
        [ordered]@{ path = $scaledOpponent; sha256 = $scaledSha },
        [ordered]@{ path = $bbOpponent; sha256 = $bbSha },
        [ordered]@{ path = $originalOpponent; sha256 = $originalSha }
    )
    optimizer = 'fresh AdamW'
    learning_rate = 0.000001
    preflop_head_learning_rate = 0.0000003
    source_policy_kl_coef = 8.0
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
