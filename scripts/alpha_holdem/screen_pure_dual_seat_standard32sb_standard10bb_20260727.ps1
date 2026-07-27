$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$candidate = (
    Resolve-Path -LiteralPath (
        'models\dual_seat_standard32sb_standard10bb_pure_20260727\policy.pt'
    )
).Path
$candidateSha = (
    Get-FileHash $candidate -Algorithm SHA256
).Hash.ToLowerInvariant()
if (
    $candidateSha -ne
        'ff154585163679e000b050518268c4e285d66efbefbcee3eb8207107b94cccf5'
) {
    throw 'Pure dual-seat checkpoint hash mismatch'
}
$verification = Get-Content -LiteralPath (
    'models\dual_seat_standard32sb_standard10bb_pure_20260727\' +
    'verification.json'
) -Raw | ConvertFrom-Json
if (
    -not [bool]$verification.passed -or
    -not [bool]$verification.logits_bitwise_exact -or
    -not [bool]$verification.values_bitwise_exact
) {
    throw 'Pure dual-seat verification did not pass'
}

& python -X utf8 scripts/alpha_holdem/play_slumbot.py `
    --strategy model `
    --model $candidate `
    --hands 0 `
    --device cpu `
    --policy-mode greedy
if ($LASTEXITCODE -ne 0) {
    throw 'Pure dual-seat deployment dry-run failed'
}

$runDir = Split-Path -Parent $candidate
$recordPath = Join-Path $runDir 'experiment_record.json'
$record = [ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'The exact20k seat specialization is complementary: Standard32 is ' +
        'the SB actor and Standard10 is the BB actor inside one pure network.'
    )
    evidence_basis = [ordered]@{
        standard10_exact20k_bb_bb_per_100 = -24.09
        standard10_exact20k_sb_bb_per_100 = 1.235
        standard32_exact20k_bb_bb_per_100 = -47.415
        standard32_exact20k_sb_bb_per_100 = 20.1544
        unpaired_hybrid_point_projection_bb_per_100 = -1.9678
    }
    candidate_checkpoint = $candidate
    candidate_checkpoint_sha256 = $candidateSha
    architecture = 'dual_seat_v1'
    inference_source_sha256 = [ordered]@{
        network_dual_seat = (
            '5aae29a6fd65be460d3bbd9343c69ec7d0cfec7233a7692b3eee5e33cf37d637'
        )
        play_slumbot = (
            'e6e7749298e190b4b5d78f68ecb878abea0012d8936656e44fd2bc3a9e5d9925'
        )
    }
    verification = [ordered]@{
        passed = [bool]$verification.passed
        tensor_count = [int]$verification.observed_tensor_count
        random_forward_rows = [int]$verification.random_forward_rows
        logits_bitwise_exact = [bool]$verification.logits_bitwise_exact
        values_bitwise_exact = [bool]$verification.values_bitwise_exact
    }
    new_training_hands = 0
    inherited_lineage_training_hands = 32853414
    inherited_offline_decision_samples = 750000
    policy_inference_classification = 'PURE_TRAINED'
    training_data_classification = 'SLUMBOT_ASSISTED'
    slumbot_free = $false
    pure_weight_policy = $true
    evaluator_side_overrides = $false
    formal_strength_eligible = $true
    evaluation_data_classification = 'FRESH_POST_FREEZE_ONLY'
    external_result = $null
    status = 'READY_FOR_PURE_FRESH5K'
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
}
$record | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8

$stem = 'dual_seat_standard32sb_standard10bb_pure'
$quickDir = Join-Path 'models' "bench_${stem}_fresh5k_20260727"
if (Test-Path -LiteralPath $quickDir) {
    throw "Pure dual-seat fresh5k already exists: $quickDir"
}
New-Item -ItemType Directory -Path $quickDir | Out-Null
@{
    schema = 'cardpilot.external_evaluation_isolation.v1'
    candidate_checkpoint_sha256 = $candidateSha
    evaluation_data_classification = 'FRESH_POST_FREEZE_ONLY'
    preexisting_slumbot_hands_reused = $false
    formal_strength_eligible = $true
} | ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath (
        Join-Path $quickDir 'evaluation_isolation.json'
    ) -Encoding UTF8

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $candidate `
    -Tag "${stem}_fresh5k_20260727" `
    -HandsPerSession 500 `
    -Sessions 10 `
    -OutputDir (Resolve-Path -LiteralPath $quickDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Pure dual-seat fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate $stem `
    -QuickDir $quickDir `
    -SourcePolicy $candidate `
    -OutputStem $stem `
    -TrainingMethod (
        'one pure dual-seat network: Standard32 frozen SB actor plus ' +
        'Standard10 frozen BB actor; no evaluator override'
    ) `
    -NewTrainingHands 0 `
    -InheritedLineageTrainingHands 32853414 `
    -OfflineDecisionSamples 750000 `
    -QuickPromoteBB100 -10
if ($LASTEXITCODE -ne 0) {
    throw 'Pure dual-seat promotion workflow failed'
}

$summaryPath = @(
    Get-ChildItem -LiteralPath $quickDir -Filter '*_ci_summary.json' -File
)
if ($summaryPath.Count -ne 1) {
    throw 'Pure dual-seat fresh5k did not produce one CI summary'
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
