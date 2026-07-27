[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Candidate,
    [Parameter(Mandatory = $true)][string]$QuickDir,
    [Parameter(Mandatory = $true)][string]$SourcePolicy,
    [Parameter(Mandatory = $true)][string]$OutputStem,
    [Parameter(Mandatory = $true)][string]$TrainingMethod,
    [long]$NewTrainingHands = 0,
    [long]$InheritedLineageTrainingHands = 0,
    [long]$OfflineDecisionSamples = 0,
    [double]$QuickPromoteBB100 = 0.0,
    [double]$FormalLaunchBB100 = 10.0,
    [double]$DeadlineHours = 18.0,
    [switch]$DeferFormal
)

$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$quickResolved = (Resolve-Path -LiteralPath $QuickDir).Path
$sourceResolved = (Resolve-Path -LiteralPath $SourcePolicy).Path
$deadline = (Get-Date).AddHours($DeadlineHours)
while ((Get-Date) -lt $deadline) {
    $summaries = @(
        Get-ChildItem -LiteralPath $quickResolved -Filter '*_ci_summary.json' `
            -File -ErrorAction SilentlyContinue
    )
    if ($summaries.Count -eq 1) { break }
    Start-Sleep -Seconds 30
}
$summaries = @(
    Get-ChildItem -LiteralPath $quickResolved -Filter '*_ci_summary.json' `
        -File -ErrorAction SilentlyContinue
)
if ($summaries.Count -ne 1) {
    throw "Timed out waiting for exactly one fresh5k summary in $quickResolved"
}
$quick = Get-Content -LiteralPath $summaries[0].FullName -Raw | ConvertFrom-Json
if ([int]$quick.hands -ne 5000) {
    throw "Unexpected fresh5k hand count: $($quick.hands)"
}
$promote = (
    [double]$quick.bb_per_100 -ge $QuickPromoteBB100 -and
    [double]$quick.upper_bound_bb_per_100 -gt 0.0
)
$quickDecision = [ordered]@{
    schema = 'cardpilot.promotion_decision.v1'
    candidate = $Candidate
    pure_trained_policy = $true
    quick5k_summary = $summaries[0].FullName
    quick5k_hands = [int]$quick.hands
    quick5k_bb_per_100 = [double]$quick.bb_per_100
    quick5k_ci95_lower = [double]$quick.lower_bound_bb_per_100
    quick5k_ci95_upper = [double]$quick.upper_bound_bb_per_100
    promotion_rule = "bb_per_100 >= $QuickPromoteBB100 and CI95 upper > 0"
    promote_to_fresh20k = $promote
    decided_at = (Get-Date).ToUniversalTime().ToString('o')
}
if (-not $promote) {
    $quickDecision | ConvertTo-Json -Depth 6 |
        Set-Content -LiteralPath (
            Join-Path $quickResolved 'promotion_decision.json'
        ) -Encoding UTF8
    exit 0
}

$sha = (
    Get-FileHash -LiteralPath $sourceResolved -Algorithm SHA256
).Hash.ToLowerInvariant()
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
$quickDecision.frozen_policy = (Resolve-Path -LiteralPath $frozenPolicy).Path
$quickDecision.frozen_policy_sha256 = $sha
$quickDecision | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (
        Join-Path $quickResolved 'promotion_decision.json'
    ) -Encoding UTF8

$manifest = [ordered]@{
    schema = 'cardpilot.frozen_policy.v1'
    candidate = $Candidate
    policy = (Resolve-Path -LiteralPath $frozenPolicy).Path
    sha256 = $sha
    source_policy = $sourceResolved
    new_training_hands = $NewTrainingHands
    offline_decision_samples = $OfflineDecisionSamples
    inherited_lineage_training_hands = $InheritedLineageTrainingHands
    training_method = $TrainingMethod
    observation_contract = 'v4 player-available information'
    inference_contract = '200bb greedy-direct model strategy with no evaluator action override'
    frozen_at = (Get-Date).ToUniversalTime().ToString('o')
}
$manifest | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (Join-Path $freezeDir 'manifest.json') -Encoding UTF8

$twentyDir = Join-Path 'models' "bench_${OutputStem}_pure_fresh20k_20260726"
$reuseTwenty = $false
if (Test-Path -LiteralPath $twentyDir) {
    $existingTwentySummaries = @(
        Get-ChildItem -LiteralPath $twentyDir `
            -Filter '*_ci_summary.json' -File -ErrorAction SilentlyContinue
    )
    if ($existingTwentySummaries.Count -eq 1) {
        $existingTwenty = Get-Content `
            -LiteralPath $existingTwentySummaries[0].FullName -Raw |
            ConvertFrom-Json
        if ([int]$existingTwenty.hands -eq 20000) {
            $reuseTwenty = $true
        }
    }
    if (-not $reuseTwenty) {
        throw (
            "Fresh20k output exists but is not one complete 20,000-hand " +
            "bundle: $twentyDir"
        )
    }
    Write-Output "Reusing complete existing fresh20k: $twentyDir"
} else {
    New-Item -ItemType Directory -Path $twentyDir | Out-Null
}
if (-not $reuseTwenty) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
        'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
        -ModelPath (Resolve-Path -LiteralPath $frozenPolicy).Path `
        -Tag "${OutputStem}_pure_fresh20k_20260726" `
        -HandsPerSession 1000 `
        -Sessions 20 `
        -OutputDir (Resolve-Path -LiteralPath $twentyDir).Path `
        -PolicyMode greedy `
        -Strategy model
    if ($LASTEXITCODE -ne 0) { throw 'Fresh20k benchmark failed' }
}

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
$formalEligible = (
    [double]$twenty.bb_per_100 -ge $FormalLaunchBB100 -and
    [double]$twenty.upper_bound_bb_per_100 -gt 0.0
)
$launchFormal = $formalEligible -and -not $DeferFormal
$formalDecision = [ordered]@{
    schema = 'cardpilot.formal100k_decision.v1'
    frozen_policy = (Resolve-Path -LiteralPath $frozenPolicy).Path
    frozen_policy_sha256 = $sha
    fresh20k_summary = $twentySummaries[0].FullName
    fresh20k_hands = [int]$twenty.hands
    fresh20k_bb_per_100 = [double]$twenty.bb_per_100
    fresh20k_ci95_lower = [double]$twenty.lower_bound_bb_per_100
    fresh20k_ci95_upper = [double]$twenty.upper_bound_bb_per_100
    launch_rule = "bb_per_100 >= $FormalLaunchBB100 and CI95 upper > 0"
    formal_eligible = $formalEligible
    formal_deferred = [bool]$DeferFormal
    launch_formal100k = $launchFormal
    decided_at = (Get-Date).ToUniversalTime().ToString('o')
}
$formalDecision | ConvertTo-Json -Depth 6 |
    Set-Content -LiteralPath (
        Join-Path $twentyDir 'formal100k_decision.json'
    ) -Encoding UTF8
if (-not $launchFormal) { exit 0 }

$formalDir = Join-Path 'models' "bench_${OutputStem}_pure_formal100k_20260726"
if (Test-Path -LiteralPath $formalDir) {
    throw "Formal100k output already exists: $formalDir"
}
New-Item -ItemType Directory -Path $formalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $frozenPolicy).Path `
    -Tag "${OutputStem}_pure_formal100k_20260726" `
    -HandsPerSession 5000 `
    -Sessions 20 `
    -OutputDir (Resolve-Path -LiteralPath $formalDir).Path `
    -PolicyMode greedy `
    -Strategy model
exit $LASTEXITCODE
