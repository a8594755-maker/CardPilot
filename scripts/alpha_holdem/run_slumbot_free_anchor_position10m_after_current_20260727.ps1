$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$deadline = [datetime]'2026-08-01T23:30:00'
$standardRecord = (
    'models\sourcev4_imitation_anchor_' +
    'mixedselfplay50m_from10m_20260726\experiment_record.json'
)
$positionRecord = (
    'models\sourcev4_standard10_' +
    'position_adapter_rl10m_20260727\experiment_record.json'
)
while (
    (
        -not (Test-Path -LiteralPath $standardRecord -PathType Leaf) -or
        -not (Test-Path -LiteralPath $positionRecord -PathType Leaf)
    ) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (
    -not (Test-Path -LiteralPath $standardRecord -PathType Leaf) -or
    -not (Test-Path -LiteralPath $positionRecord -PathType Leaf)
) {
    throw 'Timed out waiting for the two short GPU discovery runs to finish'
}

$source = (
    Resolve-Path -LiteralPath 'models\bc\v3_anchor_5M_d1_light\best.pt'
).Path
$sourceSha = (
    Get-FileHash -LiteralPath $source -Algorithm SHA256
).Hash.ToLowerInvariant()
$expectedSourceSha = (
    '6f9b1ce2762bcacef718824082b174afd594d28600335243aae35e41cda5ad18'
)
if ($sourceSha -ne $expectedSourceSha) {
    throw 'SLUMBOT_FREE source checkpoint hash mismatch'
}

$runId = 'slumbot_free_anchor_position10m_20260727'
$runDir = Join-Path 'models' $runId
if (Test-Path -LiteralPath $runDir) {
    throw "Clean-line run directory already exists: $runDir"
}
New-Item -ItemType Directory -Path $runDir | Out-Null
$recordPath = Join-Path $runDir 'experiment_record.json'
$startedAt = (Get-Date).ToUniversalTime().ToString('o')

$trainArgs = @(
    '-X', 'utf8', '-u', 'scripts/alpha_holdem/train_v5.py',
    '--device', 'cuda',
    '--workers', '20',
    '--hands-per-iter', '32768',
    '--total-hands', '10000000',
    '--starting-stack', '200',
    '--env-version', 'v55preflopv2v4obs',
    '--norm-layer', 'gn',
    '--lr', '0.000002',
    '--preflop-head-lr', '0.0000007',
    '--ppo-epochs', '3',
    '--ppo-target-kl', '0.005',
    '--source-policy-kl-coef', '5',
    '--separate-preflop-head',
    '--position-adapter-hidden', '256',
    '--critic-contract', 'critic_v2',
    '--autonomous-critic-v2-reset',
    '--h1-effective-stack-divisor', '200',
    '--value-coef', '1',
    '--mini-batch-size', '2048',
    '--epsilon', '0',
    '--gamma', '0.999',
    '--gae-lambda', '0.95',
    '--delta1', '3',
    '--entropy-coef', '0.001',
    '--entropy-floor', '0',
    '--k-best', '3',
    '--pool-strategy', 'latest',
    '--self-play-fraction', '1.0',
    '--opponent-assignment', 'per-group',
    '--opponent-groups', '4',
    '--mirror-self-play-deals',
    '--rollout-mode', 'multi',
    '--rollout-envs-per-worker', '40',
    '--inference-min-batch-slots', '128',
    '--inference-batch-deadline-us', '1000',
    '--snapshot-every', '100',
    '--save-interval', '20',
    '--archive-checkpoint-every', '100',
    '--run-id', $runId,
    '--run-dir', $runDir,
    '--out', (Join-Path $runDir 'latest.pt'),
    '--seed', '20260872',
    '--max-runtime-seconds', '21600',
    '--resume', $source,
    '--allow-resume',
    '--reset-hand-counter',
    '--reset-optimizer'
)

[ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    run_id = $runId
    status = 'RUNNING'
    hypothesis = (
        'A clean heuristic-BC anchor can retain its broad poker prior while ' +
        'current critic_v2 PPO, explicit public position, mirrored deals and ' +
        'a strong source KL learn a stronger policy without any Slumbot action data.'
    )
    material_change = (
        'Migrate the clean heuristic_v3 BC anchor to the current observation ' +
        'and position-capable network, then train 10M 100%-self-play hands ' +
        'with no fixed Slumbot-imitation opponents.'
    )
    comparison_baseline = (
        'Historical clean-anchor Slumbot reference approximately -44.74 bb/100; ' +
        'new evaluation will use fresh hands.'
    )
    policy_inference_classification = 'PURE_TRAINED'
    training_data_classification = 'SLUMBOT_FREE'
    slumbot_free = $true
    source_teacher = 'heuristic_v3'
    source_offline_decision_samples = 474983
    slumbot_training_decision_samples = 0
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
    new_training_hands_target = 10000000
    inherited_lineage_training_hands = 0
    exact_command = 'python ' + ($trainArgs -join ' ')
    seed = 20260872
    started_at = $startedAt
} | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8

& python @trainArgs
$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    $record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
    $record.status = 'FAILED'
    $record | Add-Member -NotePropertyName exit_code `
        -NotePropertyValue $exitCode
    $record | Add-Member -NotePropertyName finished_at `
        -NotePropertyValue (Get-Date).ToUniversalTime().ToString('o')
    $record | ConvertTo-Json -Depth 8 |
        Set-Content -LiteralPath $recordPath -Encoding UTF8
    throw "SLUMBOT_FREE 10M training failed with exit code $exitCode"
}

$manifest = Get-Content -LiteralPath (
    Join-Path $runDir 'run_manifest.json'
) -Raw | ConvertFrom-Json
$candidateHands = [int64]$manifest.total_hands
if ($candidateHands -lt 10000000) {
    throw "SLUMBOT_FREE run stopped early at $candidateHands hands"
}
$candidate = (
    Resolve-Path -LiteralPath (Join-Path $runDir 'latest.pt')
).Path
& python -X utf8 scripts/alpha_holdem/play_slumbot.py `
    --strategy model `
    --model $candidate `
    --hands 0 `
    --device cpu `
    --policy-mode greedy
if ($LASTEXITCODE -ne 0) {
    throw 'SLUMBOT_FREE endpoint deployment dry-run failed'
}

$record = Get-Content -LiteralPath $recordPath -Raw | ConvertFrom-Json
$record.status = 'READY_FOR_PURE_FRESH5K'
$record | Add-Member -NotePropertyName new_training_hands `
    -NotePropertyValue $candidateHands
$record | Add-Member -NotePropertyName candidate_checkpoint `
    -NotePropertyValue $candidate
$record | Add-Member -NotePropertyName candidate_checkpoint_sha256 `
    -NotePropertyValue (
        Get-FileHash -LiteralPath $candidate -Algorithm SHA256
    ).Hash.ToLowerInvariant()
$record | Add-Member -NotePropertyName finished_at `
    -NotePropertyValue (Get-Date).ToUniversalTime().ToString('o')
$record | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8
exit 0
