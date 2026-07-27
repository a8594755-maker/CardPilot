$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

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

$opponents = @(
    (
        Resolve-Path -LiteralPath (
            'models\sourcev4_slumbot_history_allstreet_' +
            'imitation_scale1p25m_20260727\best.pt'
        )
    ).Path,
    (
        Resolve-Path -LiteralPath (
            'models\sourcev4_slumbot_history500k_allstreet_' +
            'imitation_fullnet_bbweight3_20260726\selected.pt'
        )
    ).Path,
    (
        Resolve-Path -LiteralPath (
            'models\sourcev4_slumbot_history500k_allstreet_' +
            'imitation_fullnet_20260726\best.pt'
        )
    ).Path,
    (
        Resolve-Path -LiteralPath (
            'models\slumbot_free_anchor_position10m_20260727\latest.pt'
        )
    ).Path
)
$opponentRecords = @()
foreach ($opponent in $opponents) {
    $opponentRecords += [ordered]@{
        path = $opponent
        sha256 = (
            Get-FileHash -LiteralPath $opponent -Algorithm SHA256
        ).Hash.ToLowerInvariant()
    }
}

$stem = 'sourcev4_standard10_joint_trunk_position_diverse10m'
$runId = "${stem}_20260727"
$runDir = Join-Path 'models' $runId
$candidatePath = Join-Path $runDir 'latest.pt'
if (Test-Path -LiteralPath $runDir) {
    throw "Joint trunk-position output already exists: $runDir"
}
New-Item -ItemType Directory -Path $runDir | Out-Null

$launcherPath = $MyInvocation.MyCommand.Path
$trainerPath = (
    Resolve-Path -LiteralPath 'scripts\alpha_holdem\train_v5.py'
).Path
$networkPath = (
    Resolve-Path -LiteralPath 'scripts\alpha_holdem\network.py'
).Path
$recordPath = Join-Path $runDir 'experiment_record.json'
$record = [ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    run_id = $runId
    status = 'RUNNING'
    hypothesis = (
        'The Standard10 plateau and opposite seat trends arise partly from a ' +
        'shared representation that cannot allocate credit cleanly by public ' +
        'position. Jointly adapting the shared actor and explicit seat residuals ' +
        'against a broader league should improve both-seat generalization.'
    )
    material_change = (
        'From frozen Standard10, add two zero-initialized 256-hidden position ' +
        'residual heads and jointly train the complete shared actor, both seat ' +
        'heads, and critic for 10M hands. Use two self-play groups and four ' +
        'fixed learned styles, including one Slumbot-free opponent.'
    )
    comparison_baseline = [ordered]@{
        checkpoint_sha256 = $sourceSha
        fresh20k_bb_per_100 = -11.4275
        bb_seat_bb_per_100 = -24.09
        sb_seat_bb_per_100 = 1.235
        same_method_curve = (
            'models\sourcev4_imitation_anchor_mixedselfplay10m_20260726\' +
            'internal_stable_curve_v1_20260727\training_curve.json'
        )
    }
    source_checkpoint = $source
    source_checkpoint_sha256 = $sourceSha
    lineage_parent = 'sourcev4_imitation_anchor_mixedselfplay10m_20260726'
    fixed_opponents = $opponentRecords
    policy_inference_classification = 'PURE_TRAINED'
    training_data_classification = (
        'SLUMBOT_ASSISTED_WITH_SLUMBOT_FREE_LEAGUE_MEMBER'
    )
    new_training_hands_target = 10000000
    inherited_lineage_training_hands = 10283876
    inherited_offline_decision_samples = 750000
    trainable_actor_parameters = 'complete shared actor plus both position heads'
    position_adapter_hidden = 256
    position_adapter_only_training = $false
    sixmax_extensibility = (
        'Shared representation plus explicit public position-conditioned heads; ' +
        'the head index can be generalized to additional public seats.'
    )
    optimizer = [ordered]@{
        algorithm = 'Adam'
        reset_optimizer = $true
        learning_rate = 0.00001
        preflop_head_learning_rate = 0.000003
        ppo_epochs = 3
        ppo_target_kl = 0.006
        source_policy_kl_coef = 2.0
        critic_contract = 'critic_v2'
        gae_lambda = 0.95
        self_play_fraction = (2.0 / 6.0)
        opponent_group_count = 6
    }
    seed = 20260891
    launcher = $launcherPath
    launcher_sha256 = (
        Get-FileHash -LiteralPath $launcherPath -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    trainer_sha256 = (
        Get-FileHash -LiteralPath $trainerPath -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    network_sha256 = (
        Get-FileHash -LiteralPath $networkPath -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    evaluation_data_classification = 'FRESH_POST_FREEZE_ONLY'
    pure_weight_policy = $true
    evaluator_side_overrides = $false
    started_at = (Get-Date).ToUniversalTime().ToString('o')
}
$record | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8

& python -X utf8 -u scripts/alpha_holdem/train_v5.py `
    --device cuda `
    --workers 20 `
    --hands-per-iter 32768 `
    --total-hands 20283876 `
    --starting-stack 200 `
    --env-version v55preflopv2v4obs `
    --norm-layer gn `
    --lr 0.00001 `
    --preflop-head-lr 0.000003 `
    --ppo-epochs 3 `
    --ppo-target-kl 0.006 `
    --source-policy-kl-coef 2 `
    --separate-preflop-head `
    --position-adapter-hidden 256 `
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
    --self-play-fraction 0.3333333333333333 `
    --opponent-assignment per-group `
    --opponent-groups 6 `
    --fixed-opponent-checkpoints $opponents `
    --rollout-mode multi `
    --rollout-envs-per-worker 40 `
    --inference-min-batch-slots 128 `
    --inference-batch-deadline-us 1000 `
    --snapshot-every 100 `
    --save-interval 20 `
    --archive-checkpoint-every 100 `
    --run-id $runId `
    --run-dir $runDir `
    --out $candidatePath `
    --seed 20260891 `
    --max-runtime-seconds 21600 `
    --resume $source `
    --allow-resume `
    --reset-optimizer
if ($LASTEXITCODE -ne 0) {
    $record.status = 'FAILED'
    $record.finished_at = (Get-Date).ToUniversalTime().ToString('o')
    $record | ConvertTo-Json -Depth 10 |
        Set-Content -LiteralPath $recordPath -Encoding UTF8
    throw 'Joint trunk-position 10M training failed'
}

$candidate = (Resolve-Path -LiteralPath $candidatePath).Path
$candidateSha = (
    Get-FileHash -LiteralPath $candidate -Algorithm SHA256
).Hash.ToLowerInvariant()
$checkpointSummary = @(& python -X utf8 -c (
    'import sys,torch; ' +
    'c=torch.load(sys.argv[1],map_location=''cpu'',weights_only=False); ' +
    'print(int(c[''total_hands''])); ' +
    'print(int(c.get(''position_adapter_hidden'',0))); ' +
    'print(int(bool(c.get(''position_adapter_only_training'',False))))'
) $candidate)
if ($LASTEXITCODE -ne 0) {
    throw 'Could not inspect joint trunk-position checkpoint'
}
$totalHands = [int64]$checkpointSummary[-3]
$newTrainingHands = $totalHands - 10283876
if (
    $newTrainingHands -lt 10000000 -or
    [int]$checkpointSummary[-2] -ne 256 -or
    [int]$checkpointSummary[-1] -ne 0
) {
    throw 'Joint trunk-position checkpoint endpoint mismatch'
}

& python -X utf8 scripts/alpha_holdem/play_slumbot.py `
    --strategy model `
    --model $candidate `
    --hands 0 `
    --device cpu `
    --policy-mode greedy
if ($LASTEXITCODE -ne 0) {
    throw 'Joint trunk-position deployment dry-run failed'
}

$freezeTime = (Get-Date).ToUniversalTime().ToString('o')
$record.status = 'READY_FOR_PURE_FRESH5K'
$record.candidate_checkpoint = $candidate
$record.candidate_checkpoint_sha256 = $candidateSha
$record.candidate_frozen_at = $freezeTime
$record.new_training_hands = $newTrainingHands
$record.lineage_training_hands = $totalHands
$record.finished_at = $freezeTime
$record | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8

$quickDir = Join-Path 'models' "bench_${stem}_pure_fresh5k_20260727"
if (Test-Path -LiteralPath $quickDir) {
    throw "Joint trunk-position fresh5k output already exists: $quickDir"
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
    throw 'Joint trunk-position fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate $stem `
    -QuickDir $quickDir `
    -SourcePolicy $candidate `
    -OutputStem $stem `
    -TrainingMethod (
        'pure joint shared-trunk plus position-head PPO against 33pct ' +
        'self-play and four diverse learned opponents'
    ) `
    -NewTrainingHands $newTrainingHands `
    -InheritedLineageTrainingHands 10283876 `
    -OfflineDecisionSamples 750000 `
    -QuickPromoteBB100 -10
if ($LASTEXITCODE -ne 0) {
    throw 'Joint trunk-position promotion workflow failed'
}

$summaryPath = @(
    Get-ChildItem -LiteralPath $quickDir -Filter '*_ci_summary.json' -File
)
if ($summaryPath.Count -ne 1) {
    throw 'Joint trunk-position fresh5k did not produce one CI summary'
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
$record.finished_at = (Get-Date).ToUniversalTime().ToString('o')
$record | ConvertTo-Json -Depth 10 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8
