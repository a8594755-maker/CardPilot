$ErrorActionPreference = 'Stop'
Set-Location 'C:\Users\a8594\CardPilot'

$trainLog = 'reports\sourcev4_postflop_adapter128_rl_fast1m_20260726.stdout.log'
$model = 'models\sourcev4_postflop_adapter128_rl_fast1m_20260726\latest.pt'
$deadline = (Get-Date).AddHours(7)
while ((Get-Date) -lt $deadline) {
    if (
        (Test-Path -LiteralPath $trainLog) -and
        (Select-String -LiteralPath $trainLog -Pattern 'Done! [0-9,]+ hands' -Quiet)
    ) {
        break
    }
    $trainer = @(
        Get-CimInstance Win32_Process |
            Where-Object {
                $_.CommandLine -and
                $_.CommandLine -match 'train_v5.py' -and
                $_.CommandLine -match 'sourcev4_postflop_adapter128_rl_fast1m_20260726'
            }
    )
    if ($trainer.Count -eq 0 -and (Test-Path -LiteralPath $trainLog)) {
        throw 'Fast adapter 1M trainer exited without its completion line'
    }
    Start-Sleep -Seconds 20
}
if (
    -not (Test-Path -LiteralPath $trainLog) -or
    -not (Select-String -LiteralPath $trainLog -Pattern 'Done! [0-9,]+ hands' -Quiet)
) {
    throw 'Timed out waiting for fast adapter 1M training'
}

$curveDir = 'models\sourcev4_postflop_adapter128_rl_fast1m_20260726\internal_curve'
New-Item -ItemType Directory -Path $curveDir -Force | Out-Null
& python -X utf8 -u scripts/alpha_holdem/v5_internal_strength_probe.py `
    --checkpoint $model `
    --hands 1000 `
    --opponents aggressive call-station random `
    --max-pool-snapshots 0 `
    --device cuda `
    --starting-stack 200 `
    --seed 20260726 `
    --policy-mode greedy `
    --out-json (Join-Path $curveDir 'candidate.json') `
    --out-md (Join-Path $curveDir 'candidate.md')
if ($LASTEXITCODE -ne 0) {
    throw 'Fast adapter 1M internal probe failed'
}

$externalDir = 'models\bench_sourcev4_postflop_adapter128_rl_fast1m_pure_fresh5k_20260726'
if (Test-Path -LiteralPath $externalDir) {
    throw "External output already exists: $externalDir"
}
New-Item -ItemType Directory -Path $externalDir | Out-Null
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File `
    'scripts/alpha_holdem/bench_v55_slumbot.ps1' `
    -ModelPath (Resolve-Path -LiteralPath $model).Path `
    -Tag 'sourcev4_postflop_adapter128_rl_fast1m_pure_fresh5k_20260726' `
    -HandsPerSession 1250 `
    -Sessions 4 `
    -OutputDir (Resolve-Path -LiteralPath $externalDir).Path `
    -PolicyMode greedy `
    -Strategy model
exit $LASTEXITCODE
