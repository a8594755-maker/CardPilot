$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$candidate = 'sourcev4_history500k_hero_awr_epoch1'
$quickDir = 'models\bench_sourcev4_history500k_hero_awr_selected_pure_fresh5k_20260726'
$sourcePolicy = 'models\sourcev4_history500k_hero_awr_adapter256_mappingfix_20260726\selected.pt'
$deadline = (Get-Date).AddHours(18)

while ((Get-Date) -lt $deadline) {
    $summaries = @(
        Get-ChildItem -LiteralPath $quickDir -Filter '*_ci_summary.json' -File `
            -ErrorAction SilentlyContinue
    )
    if ($summaries.Count -eq 1) { break }
    $active = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine -match
                    'bench_sourcev4_history500k_hero_awr_selected_pure_fresh5k_20260726'
            }
    )
    if ($active.Count -eq 0) {
        throw 'History500k hero-AWR fresh5k exited without one CI summary'
    }
    Start-Sleep -Seconds 30
}
$summaries = @(
    Get-ChildItem -LiteralPath $quickDir -Filter '*_ci_summary.json' -File `
        -ErrorAction SilentlyContinue
)
if ($summaries.Count -ne 1) {
    throw 'Timed out waiting for the history500k hero-AWR fresh5k summary'
}
$quick = Get-Content -LiteralPath $summaries[0].FullName -Raw | ConvertFrom-Json
if ([int]$quick.hands -ne 5000) {
    throw "Unexpected quick-screen hand count: $($quick.hands)"
}
$promote = (
    [double]$quick.bb_per_100 -ge -20.0 -and
    [double]$quick.upper_bound_bb_per_100 -gt 0.0
)
$decision = [ordered]@{
    schema = 'cardpilot.promotion_decision.v1'
    candidate = $candidate
    pure_trained_policy = $true
    quick5k_summary = $summaries[0].FullName
    quick5k_hands = [int]$quick.hands
    quick5k_bb_per_100 = [double]$quick.bb_per_100
    quick5k_ci95_lower = [double]$quick.lower_bound_bb_per_100
    quick5k_ci95_upper = [double]$quick.upper_bound_bb_per_100
    promotion_rule = 'bb_per_100 >= -20 and CI95 upper > 0'
    promote_to_fresh20k = $promote
    decided_at = (Get-Date).ToUniversalTime().ToString('o')
}
if (-not $promote) {
    $decision | ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath (Join-Path $quickDir 'promotion_decision.json') `
            -Encoding UTF8
    exit 0
}

$sourceResolved = (Resolve-Path -LiteralPath $sourcePolicy).Path
$sha = (Get-FileHash -LiteralPath $sourceResolved -Algorithm SHA256).Hash.ToLowerInvariant()
$freezeDir = Join-Path 'models\frozen_candidates' $sha
$frozenPolicy = Join-Path $freezeDir 'policy.pt'
New-Item -ItemType Directory -Path $freezeDir -Force | Out-Null
if (Test-Path -LiteralPath $frozenPolicy) {
    $existingSha = (
        Get-FileHash -LiteralPath $frozenPolicy -Algorithm SHA256
    ).Hash.ToLowerInvariant()
    if ($existingSha -ne $sha) {
        throw 'Existing frozen policy does not match its content-addressed path'
    }
} else {
    Copy-Item -LiteralPath $sourceResolved -Destination $frozenPolicy
}
if (
    (Get-FileHash -LiteralPath $frozenPolicy -Algorithm SHA256).Hash.ToLowerInvariant() `
        -ne $sha
) {
    throw 'Frozen policy hash mismatch after copy'
}
$decision.frozen_policy = (Resolve-Path -LiteralPath $frozenPolicy).Path
$decision.frozen_policy_sha256 = $sha
$decision | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (Join-Path $quickDir 'promotion_decision.json') `
        -Encoding UTF8

$manifest = [ordered]@{
    schema = 'cardpilot.frozen_policy.v1'
    candidate = $candidate
    policy = (Resolve-Path -LiteralPath $frozenPolicy).Path
    sha256 = $sha
    source_policy = $sourceResolved
    new_training_hands = 0
    offline_decision_samples = 500000
    inherited_lineage_training_hands = 1446442
    lineage_hand_accounting = '526515 actor-only + 657455 ensemble4 + 262472 PokerSkill-teacher environment hands; legacy checkpoints reset local counters at each run'
    training_method = 'advantage-weighted regression on historical hero Slumbot decisions'
    observation_contract = 'v4 player-available information'
    inference_contract = '200bb greedy-direct model strategy with no evaluator action override'
    frozen_at = (Get-Date).ToUniversalTime().ToString('o')
}
$manifest | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (Join-Path $freezeDir 'manifest.json') -Encoding UTF8

$twentyDir = 'models\bench_sourcev4_history500k_hero_awr_epoch1_pure_fresh20k_20260726'
if (Test-Path -LiteralPath $twentyDir) {
    throw "Fresh20k output already exists: $twentyDir"
}
New-Item -ItemType Directory -Path $twentyDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $frozenPolicy).Path `
    -Tag 'sourcev4_history500k_hero_awr_epoch1_pure_fresh20k_20260726' `
    -HandsPerSession 2500 `
    -Sessions 8 `
    -OutputDir (Resolve-Path -LiteralPath $twentyDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) { throw 'Fresh20k benchmark failed' }

$twentySummaries = @(
    Get-ChildItem -LiteralPath $twentyDir -Filter '*_ci_summary.json' -File
)
if ($twentySummaries.Count -ne 1) {
    throw 'Fresh20k did not produce exactly one CI summary'
}
$twenty = Get-Content -LiteralPath $twentySummaries[0].FullName -Raw |
    ConvertFrom-Json
if ([int]$twenty.hands -ne 20000) {
    throw "Unexpected fresh20k hand count: $($twenty.hands)"
}
$launchFormal = (
    [double]$twenty.bb_per_100 -ge 5.0 -and
    [double]$twenty.upper_bound_bb_per_100 -gt 0.0
)
$formalDecision = [ordered]@{
    schema = 'cardpilot.formal100k_decision.v1'
    frozen_policy = (Resolve-Path -LiteralPath $frozenPolicy).Path
    frozen_policy_sha256 = $sha
    fresh20k_summary = $twentySummaries[0].FullName
    fresh20k_hands = [int]$twenty.hands
    fresh20k_bb_per_100 = [double]$twenty.bb_per_100
    fresh20k_ci95_lower = [double]$twenty.lower_bound_bb_per_100
    fresh20k_ci95_upper = [double]$twenty.upper_bound_bb_per_100
    launch_rule = 'bb_per_100 >= +5 and CI95 upper > 0'
    launch_formal100k = $launchFormal
    decided_at = (Get-Date).ToUniversalTime().ToString('o')
}
$formalDecision | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (Join-Path $twentyDir 'formal100k_decision.json') `
        -Encoding UTF8
if (-not $launchFormal) { exit 0 }

$formalDir = 'models\bench_sourcev4_history500k_hero_awr_epoch1_pure_formal100k_20260726'
if (Test-Path -LiteralPath $formalDir) {
    throw "Formal100k output already exists: $formalDir"
}
New-Item -ItemType Directory -Path $formalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $frozenPolicy).Path `
    -Tag 'sourcev4_history500k_hero_awr_epoch1_pure_formal100k_20260726' `
    -HandsPerSession 5000 `
    -Sessions 20 `
    -OutputDir (Resolve-Path -LiteralPath $formalDir).Path `
    -PolicyMode greedy `
    -Strategy model
exit $LASTEXITCODE
