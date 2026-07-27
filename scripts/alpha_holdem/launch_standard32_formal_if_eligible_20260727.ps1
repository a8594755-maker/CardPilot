$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$stem = 'sourcev4_imitation_anchor_mixedselfplay32m'
$quickDir = Join-Path 'models' "bench_${stem}_pure_fresh5k_20260727"
$quickDecisionPath = Join-Path $quickDir 'promotion_decision.json'
$deadline = [datetime]'2026-08-01T23:30:00'
while (
    -not (Test-Path -LiteralPath $quickDecisionPath -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $quickDecisionPath -PathType Leaf)) {
    throw "Timed out waiting for $quickDecisionPath"
}
$quickDecision = Get-Content -LiteralPath $quickDecisionPath -Raw |
    ConvertFrom-Json
if (-not [bool]$quickDecision.promote_to_fresh20k) {
    exit 0
}

$twentyDir = Join-Path 'models' "bench_${stem}_pure_fresh20k_20260726"
$formalDecisionPath = Join-Path $twentyDir 'formal100k_decision.json'
while (
    -not (Test-Path -LiteralPath $formalDecisionPath -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $formalDecisionPath -PathType Leaf)) {
    throw "Timed out waiting for $formalDecisionPath"
}
$formalDecision = Get-Content -LiteralPath $formalDecisionPath -Raw |
    ConvertFrom-Json
if (-not [bool]$formalDecision.formal_eligible) {
    exit 0
}

$policy = (Resolve-Path -LiteralPath $formalDecision.frozen_policy).Path
$sha = (
    Get-FileHash -LiteralPath $policy -Algorithm SHA256
).Hash.ToLowerInvariant()
if ($sha -ne [string]$formalDecision.frozen_policy_sha256) {
    throw 'Standard32 formal-policy hash mismatch'
}
$formalDir = Join-Path 'models' "bench_${stem}_pure_formal100k_20260727"
if (Test-Path -LiteralPath $formalDir) {
    throw "Standard32 formal100k output already exists: $formalDir"
}
New-Item -ItemType Directory -Path $formalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $policy `
    -Tag "${stem}_pure_formal100k_20260727" `
    -HandsPerSession 5000 `
    -Sessions 20 `
    -OutputDir (Resolve-Path -LiteralPath $formalDir).Path `
    -PolicyMode greedy `
    -Strategy model
exit $LASTEXITCODE
