$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$bbEvalDir = (
    'models\bench_sourcev4_slumbot_allstreet_' +
    'imitation_bbweight3_pure_fresh20k_20260726'
)
$bbDecisionPath = Join-Path $bbEvalDir 'formal100k_decision.json'
$deadline = [datetime]'2026-08-01T23:30:00'
while (
    -not (Test-Path -LiteralPath $bbDecisionPath -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $bbDecisionPath -PathType Leaf)) {
    throw "Timed out waiting for $bbDecisionPath"
}
$bbDecision = Get-Content -LiteralPath $bbDecisionPath -Raw |
    ConvertFrom-Json
if ([bool]$bbDecision.launch_formal100k) {
    Write-Output (
        'BB-weighted policy entered formal100k; specialist32M screen skipped.'
    )
    exit 0
}

# The decision is written after the complete20k benchmark returns.  Still wait
# explicitly for all Slumbot workers to leave before taking the sole external
# slot.
do {
    $externalWorkers = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -match (
                    'scripts[/\\]alpha_holdem[/\\]' +
                    '(play_slumbot\.py|bench_v55_slumbot\.ps1)'
                )
            }
    )
    if ($externalWorkers.Count -eq 0) { break }
    Start-Sleep -Seconds 10
} while ((Get-Date) -lt $deadline)
if ($externalWorkers.Count -ne 0) {
    throw 'Timed out waiting for the external-evaluation slot'
}

$runDir = (
    'models\sourcev4_imitation_anchor_' +
    'specialist_mixed40m_from20m_20260726'
)
$checkpoint = Join-Path $runDir (
    'checkpoints\checkpoint_iter001000_hands000032854829.pt'
)
$checkpoint = (Resolve-Path -LiteralPath $checkpoint).Path
$stem = 'sourcev4_imitation_anchor_specialist_mixed32m'
$quickDir = Join-Path 'models' "bench_${stem}_pure_fresh5k_20260727"
if (Test-Path -LiteralPath $quickDir) {
    throw "Specialist32M fresh5k output already exists: $quickDir"
}
New-Item -ItemType Directory -Path $quickDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $checkpoint `
    -Tag "${stem}_pure_fresh5k_20260727" `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $quickDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Specialist32M fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_imitation_anchor_specialist_mixed32m' `
    -QuickDir $quickDir `
    -SourcePolicy $checkpoint `
    -OutputStem $stem `
    -TrainingMethod (
        'Slumbot-specialist-then-25pct-self-play-PPO-32.85M-milestone'
    ) `
    -NewTrainingHands 12550174 `
    -InheritedLineageTrainingHands 20304655 `
    -OfflineDecisionSamples 750000 `
    -DeferFormal
if ($LASTEXITCODE -ne 0) {
    throw 'Specialist32M promotion pipeline failed'
}

# If the specialist milestone did not even clear quick5k, use the remaining
# pre-60M idle slot for the corresponding standard-lineage milestone.  If it
# promoted, its 20k already supplies the more informative intermediate screen.
$specialistPromotion = Get-Content -LiteralPath (
    Join-Path $quickDir 'promotion_decision.json'
) -Raw | ConvertFrom-Json
if ([bool]$specialistPromotion.promote_to_fresh20k) {
    exit 0
}

$standardRunDir = (
    'models\sourcev4_imitation_anchor_' +
    'mixedselfplay50m_from10m_20260726'
)
$standardCheckpoint = Join-Path $standardRunDir (
    'checkpoints\checkpoint_iter001000_hands000032853414.pt'
)
$standardCheckpoint = (
    Resolve-Path -LiteralPath $standardCheckpoint
).Path
$standardStem = 'sourcev4_imitation_anchor_mixedselfplay32m'
$standardQuickDir = Join-Path (
    'models'
) "bench_${standardStem}_pure_fresh5k_20260727"
if (Test-Path -LiteralPath $standardQuickDir) {
    throw "Standard32M fresh5k output already exists: $standardQuickDir"
}
New-Item -ItemType Directory -Path $standardQuickDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath $standardCheckpoint `
    -Tag "${standardStem}_pure_fresh5k_20260727" `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $standardQuickDir).Path `
    -PolicyMode greedy `
    -Strategy model
if ($LASTEXITCODE -ne 0) {
    throw 'Standard32M fresh5k failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_imitation_anchor_mixedselfplay32m' `
    -QuickDir $standardQuickDir `
    -SourcePolicy $standardCheckpoint `
    -OutputStem $standardStem `
    -TrainingMethod (
        'imitation-anchor-40pct-self-play-PPO-32.85M-milestone'
    ) `
    -NewTrainingHands 22569538 `
    -InheritedLineageTrainingHands 10283876 `
    -OfflineDecisionSamples 750000 `
    -QuickPromoteBB100 -10 `
    -DeferFormal
exit $LASTEXITCODE
