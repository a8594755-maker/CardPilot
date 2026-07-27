$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$quickDir = (
    'models\bench_dual_seat_standard32sb_standard10bb_pure_' +
    'fresh5k_20260727'
)
$decisionPath = Join-Path $quickDir 'promotion_decision.json'
$deadline = [datetime]'2026-08-01T23:30:00'
while (
    -not (Test-Path -LiteralPath $decisionPath -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $decisionPath -PathType Leaf)) {
    throw 'Timed out waiting for dual-seat fresh5k decision'
}
$decision = Get-Content -LiteralPath $decisionPath -Raw | ConvertFrom-Json
if ([bool]$decision.promote_to_fresh20k) {
    Write-Output 'Dual-seat already promoted under the normal fresh5k rule.'
    exit 0
}
if (
    [double]$decision.quick5k_bb_per_100 -lt -30 -or
    [double]$decision.quick5k_ci95_upper -le 0
) {
    Write-Output 'Dual-seat is not plausible under the bounded backup rule.'
    exit 0
}

$candidate = (
    Resolve-Path -LiteralPath (
        'models\dual_seat_standard32sb_standard10bb_pure_20260727\policy.pt'
    )
).Path
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'dual_seat_standard32sb_standard10bb_pure' `
    -QuickDir $quickDir `
    -SourcePolicy $candidate `
    -OutputStem 'dual_seat_standard32sb_standard10bb_pure' `
    -TrainingMethod (
        'one pure dual-seat network: Standard32 frozen SB actor plus ' +
        'Standard10 frozen BB actor; no evaluator override'
    ) `
    -NewTrainingHands 0 `
    -InheritedLineageTrainingHands 32853414 `
    -OfflineDecisionSamples 750000 `
    -QuickPromoteBB100 -30
if ($LASTEXITCODE -ne 0) {
    throw 'Dual-seat bounded backup exact20k workflow failed'
}
