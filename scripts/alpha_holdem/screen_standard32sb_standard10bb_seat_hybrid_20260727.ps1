$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$sbModel = (
    Resolve-Path -LiteralPath (
        'models\frozen_candidates\' +
        'b5a4cc970e206303280278425bd99684ebdab80c2dba07575b9bb7deb602f78c\' +
        'policy.pt'
    )
).Path
$bbModel = (
    Resolve-Path -LiteralPath (
        'models\sourcev4_imitation_anchor_' +
        'mixedselfplay10m_20260726\latest.pt'
    )
).Path
$sbSha = (Get-FileHash $sbModel -Algorithm SHA256).Hash.ToLowerInvariant()
$bbSha = (Get-FileHash $bbModel -Algorithm SHA256).Hash.ToLowerInvariant()
if (
    $sbSha -ne
        'b5a4cc970e206303280278425bd99684ebdab80c2dba07575b9bb7deb602f78c'
) {
    throw 'Standard32 SB checkpoint hash mismatch'
}
if (
    $bbSha -ne
        '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
) {
    throw 'Standard10 BB checkpoint hash mismatch'
}

$stem = 'standard32sb_standard10bb_seat_hybrid'
$runDir = Join-Path 'models' "${stem}_20260727"
$quickDir = Join-Path 'models' "bench_${stem}_diagnostic_fresh5k_20260727"
if (Test-Path -LiteralPath $runDir) {
    throw "Seat-hybrid record already exists: $runDir"
}
if (Test-Path -LiteralPath $quickDir) {
    throw "Seat-hybrid fresh5k already exists: $quickDir"
}
New-Item -ItemType Directory -Path $runDir | Out-Null
New-Item -ItemType Directory -Path $quickDir | Out-Null

$recordPath = Join-Path $runDir 'experiment_record.json'
$record = [ordered]@{
    schema = 'cardpilot.discovery_experiment.v1'
    hypothesis = (
        'The externally observed seat specialization is complementary: use ' +
        'frozen Standard32 for SB and frozen Standard10 for BB.'
    )
    evidence_basis = [ordered]@{
        standard10_exact20k_bb_bb_per_100 = -24.09
        standard10_exact20k_sb_bb_per_100 = 1.235
        standard32_exact20k_bb_bb_per_100 = -47.415
        standard32_exact20k_sb_bb_per_100 = 20.1544
        unpaired_hybrid_point_projection_bb_per_100 = -1.9678
    }
    sb_checkpoint = $sbModel
    sb_checkpoint_sha256 = $sbSha
    bb_checkpoint = $bbModel
    bb_checkpoint_sha256 = $bbSha
    policy_inference_classification = 'RUNTIME_SEAT_HYBRID_DIAGNOSTIC'
    training_data_classification = 'SLUMBOT_ASSISTED'
    slumbot_free = $false
    pure_weight_policy = $false
    formal_strength_eligible = $false
    diagnostic_only = $true
    evaluation_data_classification = 'FRESH_POST_FREEZE_ONLY'
    external_result = $null
    next_if_directional_pass = (
        'Build and independently verify a single frozen pure-weight dual-seat ' +
        'policy before any formal-eligible evaluation.'
    )
    status = 'READY_FOR_DIAGNOSTIC_FRESH5K'
    recorded_at = (Get-Date).ToUniversalTime().ToString('o')
}
$record | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8

@{
    schema = 'cardpilot.external_evaluation_isolation.v1'
    sb_checkpoint_sha256 = $sbSha
    bb_checkpoint_sha256 = $bbSha
    evaluation_data_classification = 'FRESH_POST_FREEZE_ONLY'
    preexisting_slumbot_hands_reused = $false
    formal_strength_eligible = $false
} | ConvertTo-Json -Depth 4 |
    Set-Content -LiteralPath (
        Join-Path $quickDir 'evaluation_isolation.json'
    ) -Encoding UTF8

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -Tag "${stem}_diagnostic_fresh5k_20260727" `
    -HandsPerSession 500 `
    -Sessions 10 `
    -OutputDir (Resolve-Path -LiteralPath $quickDir).Path `
    -PolicyMode greedy `
    -Strategy seat_hybrid `
    -SbModel $sbModel `
    -BbModel $bbModel
if ($LASTEXITCODE -ne 0) {
    throw 'Standard32-SB/Standard10-BB diagnostic fresh5k failed'
}

$summaryPath = @(
    Get-ChildItem -LiteralPath $quickDir -Filter '*_ci_summary.json' -File
)
if ($summaryPath.Count -ne 1) {
    throw 'Seat-hybrid fresh5k did not produce exactly one CI summary'
}
$summary = Get-Content -LiteralPath $summaryPath[0].FullName -Raw |
    ConvertFrom-Json
$record.external_result = [ordered]@{
    hands = [int]$summary.hands
    bb_per_100 = [double]$summary.bb_per_100
    ci95_lower = [double]$summary.lower_bound_bb_per_100
    ci95_upper = [double]$summary.upper_bound_bb_per_100
    summary = $summaryPath[0].FullName
}
$record.status = if (
    [double]$summary.bb_per_100 -gt -10 -and
    [double]$summary.upper_bound_bb_per_100 -gt 0
) {
    'DIRECTIONAL_PASS_BUILD_PURE_WEIGHT_POLICY'
} else {
    'DIAGNOSTIC_REJECT'
}
$record.recorded_at = (Get-Date).ToUniversalTime().ToString('o')
$record | ConvertTo-Json -Depth 8 |
    Set-Content -LiteralPath $recordPath -Encoding UTF8
