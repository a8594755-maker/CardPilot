$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$gate = (
    'models\mediumpreflop_heroawr_slumbot_mimicv2_' +
    'postflop_3p28m_20260726\experiment_record.json'
)
$deadline = (Get-Date).AddHours(2)
while (
    -not (Test-Path -LiteralPath $gate -PathType Leaf) -and
    (Get-Date) -lt $deadline
) {
    Start-Sleep -Seconds 20
}
if (-not (Test-Path -LiteralPath $gate -PathType Leaf)) {
    throw 'Timed out waiting for reach-matched endpoint'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (
    Resolve-Path -LiteralPath (
        'scripts\alpha_holdem\' +
        'run_sourcev4_heroawr_mimicv2_' +
        'bbpostflop_3p28m_20260726.ps1'
    )
).Path
exit $LASTEXITCODE
