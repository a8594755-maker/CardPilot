$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$activeBenchPid = 15652
$activePromoterPid = 49624
while (Get-Process -Id $activeBenchPid -ErrorAction SilentlyContinue) {
    Start-Sleep -Seconds 20
}
while (Get-Process -Id $activePromoterPid -ErrorAction SilentlyContinue) {
    Start-Sleep -Seconds 5
}

$tag = 'sourcev4_imitation_anchor_mixedselfplay32m_pure_fresh20k_20260726'
$bundleDir = (
    'models\bench_sourcev4_imitation_anchor_' +
    'mixedselfplay32m_pure_fresh20k_20260726'
)
$handFiles = @(
    Get-ChildItem -LiteralPath $bundleDir `
        -Filter "bench_v55_${tag}_part*_hands.jsonl" -File
)
$hands = 0
foreach ($file in $handFiles) {
    $hands += (
        Get-Content -LiteralPath $file.FullName | Measure-Object -Line
    ).Lines
}
if ($hands -eq 20000) {
    Write-Output 'Standard32 fresh20k completed exactly; no repair needed.'
    exit 0
}
if ($hands -gt 20000) {
    throw "Standard32 fresh20k has too many hands: $hands"
}

$candidate = (
    Resolve-Path -LiteralPath (
        'models\frozen_candidates\' +
        'b5a4cc970e206303280278425bd99684e' +
        'bdab80c2dba07575b9bb7deb602f78c\policy.pt'
    )
).Path
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/complete_slumbot_bundle.ps1' `
    -Candidate $candidate `
    -BundleDir $bundleDir `
    -Tag $tag `
    -TargetHands 20000 `
    -RepairDir (
        'models\bench_sourcev4_imitation_anchor_' +
        'mixedselfplay32m_pure_fresh20k_20260726_repair'
    )
if ($LASTEXITCODE -ne 0) {
    throw 'Standard32 exact fresh20k repair failed'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/promote_fresh5k_candidate.ps1' `
    -Candidate 'sourcev4_imitation_anchor_mixedselfplay32m' `
    -QuickDir (
        'models\bench_sourcev4_imitation_anchor_' +
        'mixedselfplay32m_pure_fresh5k_20260727'
    ) `
    -SourcePolicy (
        'models\sourcev4_imitation_anchor_' +
        'mixedselfplay50m_from10m_20260726\checkpoints\' +
        'checkpoint_iter001000_hands000032853414.pt'
    ) `
    -OutputStem 'sourcev4_imitation_anchor_mixedselfplay32m' `
    -TrainingMethod (
        'imitation-anchor-40pct-self-play-PPO-32.85M-milestone'
    ) `
    -NewTrainingHands 22569538 `
    -InheritedLineageTrainingHands 10283876 `
    -OfflineDecisionSamples 750000 `
    -QuickPromoteBB100 -10
exit $LASTEXITCODE
