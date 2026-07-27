$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$deadline = [datetime]'2026-08-01T23:30:00'
$sourceRecordPath = (
    'models\sourcev4_standard10_bb_only_position_adapter10m_20260727\' +
    'experiment_record.json'
)
$sourceRecord = $null
do {
    if (Test-Path -LiteralPath $sourceRecordPath -PathType Leaf) {
        try {
            $observed = Get-Content -LiteralPath $sourceRecordPath -Raw |
                ConvertFrom-Json
            if (
                -not [string]::IsNullOrWhiteSpace(
                    [string]$observed.candidate_checkpoint
                ) -and
                -not [string]::IsNullOrWhiteSpace(
                    [string]$observed.candidate_checkpoint_sha256
                )
            ) {
                $sourceRecord = $observed
                break
            }
        } catch {
            if ((Get-Date) -ge $deadline) { throw }
            $observed = $null
        }
        if (
            $null -ne $observed -and
            [string]$observed.status -eq 'FAILED'
        ) {
            throw 'First BB position-adapter endpoint failed'
        }
    }
    Start-Sleep -Seconds 20
} while ((Get-Date) -lt $deadline)
if ($null -eq $sourceRecord) {
    throw 'Timed out waiting for first BB position-adapter endpoint'
}

$source = (
    Resolve-Path -LiteralPath (
        [string]$sourceRecord.candidate_checkpoint
    )
).Path
$sourceSha = (
    Get-FileHash -LiteralPath $source -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($sourceSha -ne [string]$sourceRecord.candidate_checkpoint_sha256) {
    throw 'First BB position-adapter checkpoint hash mismatch'
}
$sourceSummary = @(& python -X utf8 -c (
    'import sys,torch; ' +
    'c=torch.load(sys.argv[1],map_location=''cpu'',weights_only=False); ' +
    'print(int(c[''total_hands''])); ' +
    'print(int(c.get(''position_adapter_hidden'',0))); ' +
    'print(int(bool(c.get(''position_adapter_only_training'',False)))); ' +
    'print(str(c.get(''position_adapter_training_seat'',''all'')))'
) $source)
if ($LASTEXITCODE -ne 0) {
    throw 'Could not inspect first BB position-adapter checkpoint'
}
$sourceHands = [int64]$sourceSummary[-4]
if (
    [int]$sourceSummary[-3] -ne 256 -or
    [int]$sourceSummary[-2] -ne 1 -or
    [string]$sourceSummary[-1] -ne 'bb'
) {
    throw 'First BB position-adapter checkpoint metadata mismatch'
}

$scaledRecord = Get-Content -LiteralPath (
    'models\sourcev4_slumbot_history_allstreet_' +
    'imitation_scale1p25m_20260727\experiment_record.json'
) -Raw | ConvertFrom-Json
$scaledOpponent = (
    Resolve-Path -LiteralPath (
        [string]$scaledRecord.candidate_checkpoint
    )
).Path
$bbRecord = Get-Content -LiteralPath (
    'models\sourcev4_slumbot_history500k_allstreet_' +
    'imitation_fullnet_bbweight3_20260726\experiment_record.json'
) -Raw | ConvertFrom-Json
$bbOpponent = (
    Resolve-Path -LiteralPath (
        [string]$bbRecord.selected_checkpoint
    )
).Path
$originalRecord = Get-Content -LiteralPath (
    'models\sourcev4_slumbot_history500k_allstreet_' +
    'imitation_fullnet_20260726\experiment_record.json'
) -Raw | ConvertFrom-Json
$originalOpponent = (
    Resolve-Path -LiteralPath (
        [string]$originalRecord.candidate_checkpoint
    )
).Path
$opponents = @($scaledOpponent, $bbOpponent, $originalOpponent)
$opponentRecords = @()
foreach ($opponent in $opponents) {
    $opponentRecords += [ordered]@{
        path = $opponent
        sha256 = (
            Get-FileHash -LiteralPath $opponent -Algorithm SHA256
        ).Hash.ToLowerInvariant()
    }
}
if (
    $opponentRecords[0].sha256 -ne
        [string]$scaledRecord.candidate_checkpoint_sha256 -or
    $opponentRecords[1].sha256 -ne
        [string]$bbRecord.selected_checkpoint_sha256 -or
    $opponentRecords[2].sha256 -ne
        [string]$originalRecord.candidate_checkpoint_sha256
) {
    throw 'Aggressive BB opponent checkpoint hash mismatch'
}

$stem = 'sourcev4_standard10_bb_only_position_adapter_aggressive10m_after10m'
$runDir = Join-Path 'models' "${stem}_20260727"
$candidatePath = Join-Path $runDir 'latest.pt'
if (Test-Path -LiteralPath $runDir) {
    throw "Aggressive BB output already exists: $runDir"
}
New-Item -ItemType Directory -Path $runDir | Out-Null
$targetHands = $sourceHands + 10000000
$recordPath = Join-Path $runDir 'experiment_record.json'
$record = [ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    run_id = "${stem}_20260727"
    status = 'RUNNING'
    hypothesis = (
        'The first isolated BB residual is behaviorally too conservative. ' +
        'A second 10M window with lower source KL, higher adapter learning ' +
        'rate, and BB-focused learned opponents can make a material BB ' +
        'policy correction while the inherited actor and SB stay frozen.'
    )
    material_change = (
        'Continue from the frozen first BB residual for 10M more hands; ' +
        'train only BB residual plus critic at lr=1e-4, source KL=0.5, ' +
        'target KL=0.01 against 25pct self-play, scaled, BB-weighted, and ' +
        'original learned Slumbot opponents.'
    )
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
    inherited_lineage_training_hands = $sourceHands
    target_new_training_hands = 10000000
    target_lineage_training_hands = $targetHands
    inherited_offline_decision_samples = 750000
    opponent_model_offline_decision_samples = (
        [int64]$scaledRecord.offline_decision_samples
    )
    fixed_opponents = $opponentRecords
    optimizer = 'fresh AdamW'
    learning_rate = 0.0001
    source_policy_kl_coef = 0.5
    ppo_target_kl = 0.01
    self_play_fraction = 0.25
    opponent_group_count = 4
    position_adapter_training_seat = 'bb'
    inherited_actor_frozen = $true
    sb_residual_frozen = $true
    seed = 20260879
    policy_inference_classification = 'PURE_TRAINED'
    training_data_classification = 'SLUMBOT_ASSISTED'
    evaluation_data_classification = 'SLUMBOT_EVAL_CONTAMINATED'
    fresh_external_evaluation_required = $true
    external_result = $null
    started_at = (Get-Date).ToUniversalTime().ToString('o')
}
$record | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8

& python -X utf8 -u scripts/alpha_holdem/train_v5.py `
    --device cuda `
    --workers 20 `
    --hands-per-iter 32768 `
    --total-hands $targetHands `
    --starting-stack 200 `
    --env-version v55preflopv2v4obs `
    --norm-layer gn `
    --lr 0.0001 `
    --ppo-epochs 3 `
    --ppo-target-kl 0.01 `
    --source-policy-kl-coef 0.5 `
    --separate-preflop-head `
    --position-adapter-hidden 256 `
    --position-adapter-only-training `
    --position-adapter-training-seat bb `
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
    --self-play-fraction 0.25 `
    --opponent-assignment per-group `
    --opponent-groups 4 `
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
    --seed 20260879 `
    --max-runtime-seconds 21600 `
    --resume $source `
    --allow-resume `
    --reset-optimizer
if ($LASTEXITCODE -ne 0) {
    $record.status = 'FAILED'
    $record.finished_at = (Get-Date).ToUniversalTime().ToString('o')
    $record | ConvertTo-Json -Depth 10 |
        Set-Content -LiteralPath $recordPath -Encoding UTF8
    throw 'Aggressive BB position-adapter training failed'
}

$candidate = (Resolve-Path -LiteralPath $candidatePath).Path
$candidateSha = (
    Get-FileHash -LiteralPath $candidate -Algorithm SHA256
).Hash.ToLowerInvariant()
$candidateSummary = @(& python -X utf8 -c (
    'import sys,torch; ' +
    'c=torch.load(sys.argv[1],map_location=''cpu'',weights_only=False); ' +
    'print(int(c[''total_hands''])); ' +
    'print(int(c.get(''position_adapter_hidden'',0))); ' +
    'print(int(bool(c.get(''position_adapter_only_training'',False)))); ' +
    'print(str(c.get(''position_adapter_training_seat'',''all'')))'
) $candidate)
if ($LASTEXITCODE -ne 0) {
    throw 'Could not inspect aggressive BB checkpoint'
}
$candidateHands = [int64]$candidateSummary[-4]
$newTrainingHands = $candidateHands - $sourceHands
if (
    $newTrainingHands -lt 10000000 -or
    [int]$candidateSummary[-3] -ne 256 -or
    [int]$candidateSummary[-2] -ne 1 -or
    [string]$candidateSummary[-1] -ne 'bb'
) {
    throw 'Aggressive BB checkpoint endpoint mismatch'
}

& python -X utf8 scripts/alpha_holdem/play_slumbot.py `
    --strategy model `
    --model $candidate `
    --hands 0 `
    --device cpu `
    --policy-mode greedy
if ($LASTEXITCODE -ne 0) {
    throw 'Aggressive BB deployment dry-run failed'
}

$freezeTime = (Get-Date).ToUniversalTime().ToString('o')
$record.status = 'READY_FOR_PURE_FRESH5K'
$record.candidate_checkpoint = $candidate
$record.candidate_checkpoint_sha256 = $candidateSha
$record.candidate_frozen_at = $freezeTime
$record.new_training_hands = $newTrainingHands
$record.lineage_training_hands = $candidateHands
$record.finished_at = $freezeTime
$record | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8

$quickDir = Join-Path 'models' "bench_${stem}_pure_fresh5k_20260727"
if (Test-Path -LiteralPath $quickDir) {
    throw "Aggressive BB fresh5k output already exists: $quickDir"
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
    throw 'Aggressive BB fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate $stem `
    -QuickDir $quickDir `
    -SourcePolicy $candidate `
    -OutputStem $stem `
    -TrainingMethod (
        'aggressive pure BB-only position residual continuation; inherited ' +
        'actor and SB residual frozen'
    ) `
    -NewTrainingHands $newTrainingHands `
    -InheritedLineageTrainingHands $sourceHands `
    -OfflineDecisionSamples 750000 `
    -QuickPromoteBB100 -10
if ($LASTEXITCODE -ne 0) {
    throw 'Aggressive BB promotion workflow failed'
}

$summaryPath = @(
    Get-ChildItem -LiteralPath $quickDir -Filter '*_ci_summary.json' -File
)
if ($summaryPath.Count -ne 1) {
    throw 'Aggressive BB fresh5k did not produce one CI summary'
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
$record | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8
