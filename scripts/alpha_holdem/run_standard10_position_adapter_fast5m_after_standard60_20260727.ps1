$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

# Reuse the GPU slot released by Standard60.  The conservative position run
# remains independent; this faster residual tests whether its early ~1e-4 KL
# movement is simply underpowered.
$slotMarker = (
    'models\sourcev4_imitation_anchor_' +
    'mixedselfplay50m_from10m_20260726\experiment_record.json'
)
$deadline = [datetime]'2026-08-01T23:30:00'
while (
    -not (Test-Path -LiteralPath $slotMarker -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $slotMarker -PathType Leaf)) {
    throw 'Timed out waiting for the Standard60 GPU slot'
}

$source = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_imitation_anchor_' +
        'mixedselfplay10m_20260726\latest.pt'
    )
).Path
$sourceSha = (
    Get-FileHash -LiteralPath $source -Algorithm SHA256
).Hash.ToLowerInvariant()
if (
    $sourceSha -ne
        '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
) {
    throw 'Standard10 source checkpoint hash mismatch'
}

$opponentRoot = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_slumbot_history500k_' +
        'allstreet_imitation_fullnet_20260726'
    )
).Path
$opponents = @(
    (Join-Path $opponentRoot 'best.pt'),
    (Join-Path $opponentRoot 'epoch_7.pt'),
    (Join-Path $opponentRoot 'epoch_6.pt')
)
foreach ($opponent in $opponents) {
    if (-not (Test-Path -LiteralPath $opponent -PathType Leaf)) {
        throw "Missing fixed opponent: $opponent"
    }
}

$stem = 'sourcev4_standard10_position_adapter_fast5m'
$runDir = Join-Path 'models' "${stem}_20260727"
$candidatePath = Join-Path $runDir 'latest.pt'
if (Test-Path -LiteralPath $runDir) {
    throw "Fast position-adapter output already exists: $runDir"
}

& python -X utf8 -u scripts/alpha_holdem/train_v5.py `
    --device cuda `
    --workers 20 `
    --hands-per-iter 32768 `
    --total-hands 15283876 `
    --starting-stack 200 `
    --env-version v55preflopv2v4obs `
    --norm-layer gn `
    --lr 0.00005 `
    --ppo-epochs 3 `
    --ppo-target-kl 0.005 `
    --source-policy-kl-coef 2 `
    --separate-preflop-head `
    --position-adapter-hidden 256 `
    --position-adapter-only-training `
    --critic-contract critic_v2 `
    --autonomous-critic-v2-continue `
    --h1-effective-stack-divisor 200 `
    --value-coef 1 `
    --mini-batch-size 2048 `
    --epsilon 0 `
    --gamma 0.999 `
    --gae-lambda 0.95 `
    --delta1 3 `
    --entropy-coef 0.001 `
    --entropy-floor 0 `
    --k-best 3 `
    --pool-strategy latest `
    --self-play-fraction 0.4 `
    --opponent-assignment per-group `
    --opponent-groups 5 `
    --fixed-opponent-checkpoints $opponents `
    --rollout-mode multi `
    --rollout-envs-per-worker 40 `
    --inference-min-batch-slots 128 `
    --inference-batch-deadline-us 1000 `
    --snapshot-every 100 `
    --save-interval 20 `
    --archive-checkpoint-every 100 `
    --run-id "${stem}_20260727" `
    --run-dir $runDir `
    --out $candidatePath `
    --seed 20260866 `
    --max-runtime-seconds 21600 `
    --resume $source `
    --allow-resume `
    --reset-optimizer
if ($LASTEXITCODE -ne 0) {
    throw 'Fast position-adapter 5M training failed'
}

$candidate = (Resolve-Path -LiteralPath $candidatePath).Path
$candidateSha = (
    Get-FileHash -LiteralPath $candidate -Algorithm SHA256
).Hash.ToLowerInvariant()
$totalHandsText = @(& python -X utf8 -c (
    'import sys,torch; ' +
    'print(int(torch.load(sys.argv[1],map_location=''cpu'',' +
    'weights_only=False)[''total_hands'']))'
) $candidate)
if ($LASTEXITCODE -ne 0) {
    throw 'Could not inspect fast position-adapter hand count'
}
$totalHands = [int64]$totalHandsText[-1]
$newTrainingHands = $totalHands - 10283876
if ($newTrainingHands -lt 5000000) {
    throw "Fast position-adapter run stopped early at $newTrainingHands new hands"
}

& python -X utf8 scripts/alpha_holdem/play_slumbot.py `
    --strategy model `
    --model $candidate `
    --hands 0 `
    --device cpu `
    --policy-mode greedy
if ($LASTEXITCODE -ne 0) {
    throw 'Fast position-adapter deployment dry-run failed'
}

$recordPath = Join-Path $runDir 'experiment_record.json'
$freezeTime = (Get-Date).ToUniversalTime().ToString('o')
$record = [ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'The conservative position residual moves too slowly at about 8e-5 ' +
        'source KL after 0.89M new hands. A five-times larger residual LR and ' +
        'weaker but material KL=2 guard should reach a useful position-specific ' +
        'policy displacement in 5M environment hands.'
    )
    material_change = (
        'From the same frozen Standard10 actor, train only two zero-residual ' +
        '256-hidden seat experts plus critic for 5M hands with lr=5e-5 and ' +
        'source-policy KL coefficient 2; all shared actor tensors stay frozen.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
    candidate_checkpoint = $candidate
    candidate_checkpoint_sha256 = $candidateSha
    new_training_hands = $newTrainingHands
    inherited_lineage_training_hands = 10283876
    inherited_offline_decision_samples = 750000
    policy_inference_classification = 'PURE_TRAINED'
    training_data_classification = 'SLUMBOT_ASSISTED'
    slumbot_free = $false
    evaluation_data_classification = 'FRESH_POST_FREEZE_ONLY'
    same_or_earlier_slumbot_hands_forbidden = $true
    candidate_frozen_at = $freezeTime
    pure_weight_policy = $true
    evaluator_side_overrides = $false
    external_result = $null
    status = 'READY_FOR_PURE_FRESH5K'
    recorded_at = $freezeTime
}
$record | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8

$quickDir = Join-Path 'models' "bench_${stem}_pure_fresh5k_20260727"
if (Test-Path -LiteralPath $quickDir) {
    throw "Fast position-adapter fresh5k output already exists: $quickDir"
}
New-Item -ItemType Directory -Path $quickDir | Out-Null
@{
    schema = 'cardpilot.external_evaluation_isolation.v1'
    candidate_checkpoint_sha256 = $candidateSha
    candidate_frozen_at = $freezeTime
    evaluation_data_classification = 'FRESH_POST_FREEZE_ONLY'
    pre_freeze_slumbot_hands_forbidden = $true
} | ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath (
        Join-Path $quickDir 'evaluation_isolation.json'
    ) -Encoding UTF8
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $candidate `
    -Tag "${stem}_pure_fresh5k_20260727" `
    -HandsPerSession 500 `
    -Sessions 10 `
    -OutputDir (Resolve-Path -LiteralPath $quickDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Fast position-adapter fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate $stem `
    -QuickDir $quickDir `
    -SourcePolicy $candidate `
    -OutputStem $stem `
    -TrainingMethod (
        'pure fast position-residual PPO on 40pct self-play plus three learned ' +
        'Slumbot opponents; inherited actor frozen'
    ) `
    -NewTrainingHands $newTrainingHands `
    -InheritedLineageTrainingHands 10283876 `
    -OfflineDecisionSamples 750000 `
    -QuickPromoteBB100 -10
if ($LASTEXITCODE -ne 0) {
    throw 'Fast position-adapter promotion workflow failed'
}

$summaryPath = @(
    Get-ChildItem -LiteralPath $quickDir -Filter '*_ci_summary.json' -File
)
if ($summaryPath.Count -ne 1) {
    throw 'Fast position-adapter fresh5k did not produce one CI summary'
}
$summary = Get-Content -LiteralPath $summaryPath[0].FullName -Raw |
    ConvertFrom-Json
$decision = Get-Content -LiteralPath (
    Join-Path $quickDir 'promotion_decision.json'
) -Raw | ConvertFrom-Json
$record.external_result = [ordered]@{
    hands = [int]$summary.hands
    bb_per_100 = [double]$summary.bb_per_100
    ci95_lower = [double]$summary.lower_bound_bb_per_100
    ci95_upper = [double]$summary.upper_bound_bb_per_100
    summary = $summaryPath[0].FullName
}
$record.status = if ([bool]$decision.promote_to_fresh20k) {
    'PROMOTED_TO_FRESH20K'
} else {
    'REJECT_EXTERNAL_FRESH5K'
}
$record.recorded_at = (Get-Date).ToUniversalTime().ToString('o')
$record | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8
